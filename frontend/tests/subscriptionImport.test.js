import assert from "node:assert/strict";
import test from "node:test";
import { getClientImportLink, getSubscriptionClients, getSubscriptionImportUrl } from "../src/utils/subscriptionImport.js";

const subscription = {
  format: "hiddify",
  url: "https://vpn.example.test:2095/api/subscriptions/fetch/fixture-token?format=hiddify",
  connect_url: "https://vpn.example.test:2095/s/fixture-token",
};

test("existing Hiddify JSON subscriptions keep their stored format", () => {
  const url = getSubscriptionImportUrl(subscription);
  assert.equal(new URL(url).pathname, "/api/subscriptions/fetch/fixture-token");
  assert.equal(new URL(url).searchParams.get("format"), "hiddify");
  assert.notEqual(url, subscription.connect_url);
  assert.equal(subscription.format, "hiddify");
});

test("an explicitly selected format preserves the subscription address and token", () => {
  const url = new URL(getSubscriptionImportUrl({ ...subscription, url: subscription.url + "&source=fixture%2Bvalue" }, "clash"));
  assert.equal(url.origin, "https://vpn.example.test:2095");
  assert.equal(url.pathname, "/api/subscriptions/fetch/fixture-token");
  assert.equal(url.searchParams.get("format"), "clash");
  assert.equal(url.searchParams.get("source"), "fixture+value");
});

test("the Hiddify import button round-trips the full nested subscription URL", () => {
  const client = getSubscriptionClients("desktop", ["base64"])[0];
  const url = getSubscriptionImportUrl(subscription, client.format);
  const link = new URL(getClientImportLink(client, url));
  assert.equal(client.id, "hiddify");
  assert.equal(client.format, "base64");
  assert.equal(link.protocol, "hiddify:");
  assert.equal(link.hostname, "install-config");
  assert.equal(link.searchParams.get("name"), "FVpn");
  assert.equal(link.searchParams.get("url"), url);
  assert.equal(new URL(link.searchParams.get("url")).searchParams.get("format"), "base64");
});

test("Streisand uses a compatible URI subscription and manual import", () => {
  const client = getSubscriptionClients("ios", ["base64", "shadowrocket"]).find((item) => item.id === "streisand");
  assert.equal(client.format, "base64");
  assert.equal(getClientImportLink(client, getSubscriptionImportUrl(subscription)), null);
  assert.equal(getSubscriptionClients("android", ["base64"]).some((item) => item.id === "streisand"), false);
});

test("client choices require a format the subscription can actually export", () => {
  assert.deepEqual(getSubscriptionClients("ios", ["clash"]), []);
  const clients = getSubscriptionClients("android", ["v2rayng"]);
  assert.deepEqual(clients.map((item) => item.id), ["v2rayng"]);
});

test("existing non-Hiddify formats remain the default when explicitly stored", () => {
  const url = getSubscriptionImportUrl({ ...subscription, format: "clash" });
  assert.equal(new URL(url).searchParams.get("format"), "clash");
});

test("ShadowTLS-only exports retain the Hiddify JSON client", () => {
  const clients = getSubscriptionClients("ios", ["singbox", "hiddify"]);
  assert.deepEqual(clients.map((item) => item.id), ["hiddify"]);
  assert.equal(clients[0].format, "hiddify");
  const data = { ...subscription, format: "base64", available_formats: ["singbox", "hiddify"] };
  const url = getSubscriptionImportUrl(data, clients[0].format);
  assert.equal(new URL(url).searchParams.get("format"), "hiddify");
  assert.equal(new URL(getClientImportLink(clients[0], url)).searchParams.get("url"), url);
});

test("an unavailable stored format falls back to an available export", () => {
  const data = { ...subscription, format: "base64", available_formats: ["clash"] };
  assert.equal(new URL(getSubscriptionImportUrl(data)).searchParams.get("format"), "clash");
});

test("new URI subscriptions remain Base64 without changing existing records", () => {
  const url = getSubscriptionImportUrl({ ...subscription, format: "base64" });
  assert.equal(new URL(url).searchParams.get("format"), "base64");
  assert.equal(subscription.format, "hiddify");
});
