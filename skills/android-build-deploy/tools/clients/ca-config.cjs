const fs = require('node:fs');
const path = require('node:path');
const { X509Certificate, createHash } = require('node:crypto');
const net = require('node:net');

function readCa(config, envFile) {
  if (config.tlsMode === 'caddy-public-acme') {
    if (config.values.CLIENT_CA_FILE) throw Error('Public TLS forbids private anchors');
    return null;
  }
  if (!config.values.CLIENT_CA_FILE) return null;
  if (!config.origin.startsWith('https:')) throw Error('CLIENT_CA_FILE requires HTTPS');
  const file = path.resolve(path.dirname(envFile), config.values.CLIENT_CA_FILE);
  const pem = fs.readFileSync(file, 'utf8');
  if (/PRIVATE KEY/.test(pem) || (pem.match(/BEGIN CERTIFICATE/g) || []).length !== 1) throw Error('CA file must contain one public certificate and no private keys');
  const cert = new X509Certificate(pem);
  if (!cert.ca || Date.parse(cert.validFrom) > Date.now() || Date.parse(cert.validTo) <= Date.now()) throw Error('CA certificate must be a currently valid authority');
  return { file, pem: cert.toString(), sha256: createHash('sha256').update(cert.raw).digest('hex'), validTo: cert.validTo };
}

function matchesCa(data, ca) {
  // Compare by certificate DER bytes so PEM line endings (LF/CRLF) never cause false mismatches.
  if (!ca || !data) return false;
  try { return createHash('sha256').update(new X509Certificate(data).raw).digest('hex') === ca.sha256; }
  catch { return false; }
}

function androidTrust(xml, host, mode = 'private-ca') {
  if (!(net.isIP(host) || /^(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$/.test(host))) throw Error('Invalid TLS host');
  const block = /<domain-config\b[^>]*>[\s\S]*?<\/domain-config>/g;
  const domain = `<domain includeSubdomains="false">${host}</domain>`;
  if (!['private-ca', 'caddy-public-acme'].includes(mode)) throw Error('Invalid TLS mode');
  const anchor = mode === 'caddy-public-acme' ? 'system' : '@raw/cloudmeet_client_ca';
  const trust = `<domain-config cleartextTrafficPermitted="false">${domain}<trust-anchors><certificates src="${anchor}" /></trust-anchors></domain-config>`;
  // Remove the configured host from an old domain group, keeping unrelated policies.
  let result = xml.replace(block, group => {
    const escaped = host.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const next = group.replace(new RegExp(`<domain\\b[^>]*>\\s*${escaped}\\s*</domain>`, 'g'), '');
    return /<domain(?:\s|>)/.test(next) ? next : '';
  });
  if (!result.includes('</network-security-config>')) throw Error('Unexpected Android trust XML');
  return result.replace(/\s*<\/network-security-config>/, trust + '\n</network-security-config>');
}
module.exports = { readCa, androidTrust, matchesCa };
