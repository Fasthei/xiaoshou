/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE: string;
  readonly VITE_CASDOOR_ENDPOINT: string;
  readonly VITE_CASDOOR_CLIENT_ID: string;
  readonly VITE_CASDOOR_ORG: string;
  readonly VITE_CASDOOR_APP: string;
  readonly VITE_CASDOOR_REDIRECT: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
