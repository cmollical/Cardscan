import { getApp, getApps, initializeApp } from "@firebase/app";
import { getAuth } from "@firebase/auth";

const config = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

export const firebaseConfigured = Object.values(config).every(Boolean);
export const firebaseAuth = firebaseConfigured
  ? getAuth(getApps().length ? getApp() : initializeApp(config))
  : null;

export async function firebaseIdToken() {
  return firebaseAuth?.currentUser
    ? await firebaseAuth.currentUser.getIdToken()
    : "";
}
