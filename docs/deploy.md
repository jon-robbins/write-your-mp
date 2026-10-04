# Deploying to Google Cloud Run

This copy is not deployed. These are the steps the original campaign used, with placeholders. Set them once:

```bash
PROJECT_ID=your-project
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
REGION=us-west1          # pick the region closest to your visitors
REPO=your-github-user/write-your-mp
```

## 1. A runtime account with no permissions

The app calls no Google APIs, so it runs as an account with no roles. If the app were ever compromised, that account gives an attacker nothing.

```bash
gcloud iam service-accounts create write-your-mp-runtime --project=$PROJECT_ID \
  --display-name="write-your-mp runtime (no roles)"
```

## 2. Deploy by hand

```bash
gcloud run deploy write-your-mp --source . --project=$PROJECT_ID --region=$REGION \
  --no-invoker-iam-check --ingress=all --min-instances=0 --max-instances=2 --memory=512Mi --cpu=1 --timeout=15s \
  --service-account=write-your-mp-runtime@$PROJECT_ID.iam.gserviceaccount.com \
  --set-env-vars=FRAME_ANCESTORS="https://example.org https://www.example.org"
```

`--max-instances=2` keeps costs bounded and the Represent call rate low. `FRAME_ANCESTORS` lists the sites allowed to embed the tool. Alternatively, build and push an image and apply `deploy/cloudrun-service.yaml` with `gcloud run services replace`.

## 3. Deploy from GitHub Actions without keys

GitHub proves its identity to Google with a short-lived token, and Google lets only this repository use the deploy account.

```bash
gcloud services enable iamcredentials.googleapis.com sts.googleapis.com --project=$PROJECT_ID
gcloud iam service-accounts create github-deployer --project=$PROJECT_ID
for role in roles/run.admin roles/cloudbuild.builds.editor roles/storage.admin roles/artifactregistry.reader roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding $PROJECT_ID --member=serviceAccount:github-deployer@$PROJECT_ID.iam.gserviceaccount.com --role=$role --condition=None
done
# The deployer may run the service as the runtime account, and builds as the default compute account.
for sa in write-your-mp-runtime@$PROJECT_ID.iam.gserviceaccount.com $PROJECT_NUMBER-compute@developer.gserviceaccount.com; do
  gcloud iam service-accounts add-iam-policy-binding $sa --project=$PROJECT_ID \
    --member=serviceAccount:github-deployer@$PROJECT_ID.iam.gserviceaccount.com --role=roles/iam.serviceAccountUser
done
# Source deploys push images here; the deployer can push but not create the repository.
gcloud artifacts repositories create cloud-run-source-deploy --repository-format=docker --location=$REGION --project=$PROJECT_ID

gcloud iam workload-identity-pools create github --project=$PROJECT_ID --location=global
gcloud iam workload-identity-pools providers create-oidc github-oidc --project=$PROJECT_ID --location=global \
  --workload-identity-pool=github --issuer-uri=https://token.actions.githubusercontent.com \
  --attribute-mapping=google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref \
  --attribute-condition="assertion.repository=='$REPO' && assertion.ref=='refs/heads/main'"
gcloud iam service-accounts add-iam-policy-binding github-deployer@$PROJECT_ID.iam.gserviceaccount.com --project=$PROJECT_ID \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/attribute.repository/$REPO"
```

Then set these repository variables (Settings → Secrets and variables → Actions → Variables) and run **Deploy to Cloud Run** from the Actions tab:

| Variable | Value |
|---|---|
| `GCP_PROJECT_ID` | your project ID |
| `GCP_REGION` | e.g. `us-west1` |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github/providers/github-oidc` |
| `GCP_DEPLOY_SERVICE_ACCOUNT` | `github-deployer@PROJECT_ID.iam.gserviceaccount.com` |
| `FRAME_ANCESTORS` | sites allowed to embed the tool, space-separated |

To deploy every merge to `main` automatically, add `push: branches: [main]` under `on:` in `.github/workflows/deploy.yml`.

## 4. Embed it in a WordPress page

Paste into the page's Code editor (not Visual, which strips scripts). The script resizes the iframe to the tool's height, and only accepts messages from the tool's own origin.

```html
<iframe id="mp-letter" loading="eager" src="https://SERVICE_URL/campaign/" title="Message your MP" style="width:100%;height:1600px;border:0;display:block" allow="clipboard-write"></iframe>
<script>window.addEventListener('message',function(e){if(e.origin!=='https://SERVICE_URL'||!e.data||e.data.type!=='mp-letter:height')return;document.getElementById('mp-letter').style.height=e.data.height+'px';});</script>
```

Add the WordPress site's origin to `FRAME_ANCESTORS`, or browsers will refuse to show the iframe.
