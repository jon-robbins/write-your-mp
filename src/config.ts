export interface CampaignConfig {
  lookupUrl: string;
  letterUrl: string;
}

declare global {
  interface Window { CAMPAIGN_CONFIG?: CampaignConfig; }
}

export function getCampaignConfig(): CampaignConfig {
  return window.CAMPAIGN_CONFIG ?? { lookupUrl: '/campaign/api/lookup-mp', letterUrl: '/campaign/api/letter' };
}
