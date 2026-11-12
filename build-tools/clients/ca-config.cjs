const fs = require('node:fs');
const path = require('node:path');
const { X509Certificate, createHash } = require('node:crypto');

function readCa(config, envFile) {
  if (!config.values.CLIENT_CA_FILE) return null;
  if (!config.origin.startsWith('https:')) throw Error('CLIENT_CA_FILE requires HTTPS');
  const file = path.resolve(path.dirname(envFile), config.values.CLIENT_CA_FILE);
  const pem = fs.readFileSync(file, 'utf8');
  if (/PRIVATE KEY/.test(pem) || (pem.match(/BEGIN CERTIFICATE/g) || []).length !== 1) throw Error('CA file must contain one public certificate and no private keys');
  const cert = new X509Certificate(pem);
  if (!cert.ca || Date.parse(cert.validFrom) > Date.now() || Date.parse(cert.validTo) <= Date.now()) throw Error('CA certificate must be a currently valid authority');
  return { file, pem: cert.toString(), sha256: createHash('sha256').update(cert.raw).digest('hex'), validTo: cert.validTo };
}

function androidTrust(xml, host) {
  if (!/^[a-zA-Z0-9.-]+$/.test(host)) throw Error('Invalid TLS host');
  const block = /<domain-config\b[^>]*>[\s\S]*?<\/domain-config>/g;
  const domain = `<domain includeSubdomains="false">${host}</domain>`;
  const trust = `<domain-config cleartextTrafficPermitted="false">${domain}<trust-anchors><certificates src="@raw/cloudmeet_client_ca" /></trust-anchors></domain-config>`;
  // Remove the configured host from an old domain group, keeping unrelated policies.
  let result = xml.replace(block, group => {
    const escaped = host.replace(/\./g, '\\.');
    const next = group.replace(new RegExp(`<domain\\b[^>]*>\\s*${escaped}\\s*</domain>`, 'g'), '');
    return /<domain(?:\s|>)/.test(next) ? next : '';
  });
  if (!result.includes('</network-security-config>')) throw Error('Unexpected Android trust XML');
  return result.replace(/\s*<\/network-security-config>/, trust + '\n</network-security-config>');
}
module.exports = { readCa, androidTrust };
