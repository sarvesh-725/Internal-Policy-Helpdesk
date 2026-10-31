import Keycloak from "keycloak-js";

const keycloak = new Keycloak({
  url: import.meta.env.VITE_KEYCLOAK_URL || "http://localhost:8080",
  realm: import.meta.env.VITE_KEYCLOAK_REALM || "nodeswarm",
  clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID || "nodeswarm-web",
});

export async function initializeAuth() {
  await keycloak.init({ onLoad: "check-sso", pkceMethod: "S256", checkLoginIframe: false });
  return keycloak;
}

export async function getAccessToken() {
  if (!keycloak.authenticated) return null;
  await keycloak.updateToken(30);
  return keycloak.token || null;
}

export function signIn() {
  return keycloak.login();
}

export function signOut() {
  return keycloak.logout({ redirectUri: window.location.origin });
}
