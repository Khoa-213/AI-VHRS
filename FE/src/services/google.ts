/** Web client id of the project (same one as `GOOGLE_CLIENT` on the backend). Without it the Google button is not shown. */
export const GOOGLE_CLIENT_ID = (import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined)?.trim() ?? ''
