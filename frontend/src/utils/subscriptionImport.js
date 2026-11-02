export function getSubscriptionImportUrl(subscription, format) {
  const requestedFormat = format || subscription.format || "base64";
  const availableFormats = subscription.available_formats;
  const selectedFormat = availableFormats?.length && !availableFormats.includes(requestedFormat)
    ? availableFormats[0]
    : requestedFormat;
  const url = new URL(subscription.url);
  url.searchParams.set("format", selectedFormat);
  return url.href;
}

export function getSubscriptionClients(platform, availableFormats) {
  const clients = [];
  const hiddifyFormat = availableFormats.includes("base64") ? "base64" : availableFormats.includes("hiddify") ? "hiddify" : null;
  if (hiddifyFormat) {
    clients.push({ id: "hiddify", label: "Hiddify", format: hiddifyFormat, download: "https://hiddify.com/app/", scheme: "hiddify://install-config?name=FVpn&url=" });
  }
  if (platform === "ios" && availableFormats.includes("base64")) {
    clients.push({ id: "streisand", label: "Streisand", format: "base64", download: "https://apps.apple.com/app/streisand/id6450534064", scheme: null });
  }
  if (platform === "android" && availableFormats.includes("v2rayng")) {
    clients.push({ id: "v2rayng", label: "v2rayNG", format: "v2rayng", download: "https://github.com/2dust/v2rayNG/releases", scheme: "v2rayng://install-config?url=" });
  }
  if (platform === "ios" && availableFormats.includes("shadowrocket")) {
    clients.push({ id: "shadowrocket", label: "Shadowrocket", format: "shadowrocket", download: "https://apps.apple.com/app/shadowrocket/id932747118", scheme: null });
  }
  return clients;
}

export function getClientImportLink(client, subscriptionUrl) {
  return client?.scheme ? `${client.scheme}${encodeURIComponent(subscriptionUrl)}` : null;
}
