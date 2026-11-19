# Version policy activation — 2026-11-19

## Approval and limits

- User requested enabling the configuration switch and ultimately confirmed server baseline **11248.0.1**, not the briefly selected 11248.0.2. Client baseline remains 1.0.21.
- User explicitly approved using existing formal delivery packages as the upgrade compatibility baseline: Android code 1021 and MSI ProductVersion 1.0.21. Earlier unavailable time-counter test APKs are outside this compatibility guarantee; no claim that these are the highest versions ever installed everywhere.
- `config/version-policy.json` now has approved=true. This approves configuration only, not a product build, formal revision allocation, signing, publication, server change or an exception to a higher-version downgrade check.
- Dedicated 150 controller Runner, restricted Runner group, repository variable, external persistent ledger initialization, independent backup and recovery verification remain unconfigured/unverified. No formal ledger was initialized and no revision was consumed.

## Read-only package evidence

Read actual APK metadata with Android SDK aapt dump badging; read actual MSI Property.ProductVersion with WindowsInstaller COM OpenDatabase mode 0. SHA256 values below are from the actual package bytes, not filenames. Paths are relative to deploy/release/clients/.

| Package | Actual version | SHA256 |
|---|---|---|
| android/universal/1.0.20-20261113-7kRqh1/app-release.apk | 1.0.20 / code 1020 | c2e89f50d51effcfbfe0dfab33b29d199fc9eb480439f768bd099a7861179021 |
| android/universal/1.0.21-cloudmeet-clients-zj3lBy/app-release.apk | 1.0.21 / code 1021 | 4dce8a2884f732c1f10b5fe5173b1c4f184cf858a4f8fc3ba0fa050a0ca405ff |
| android/universal/1.0.21-cloudmeet-clients-zSQ3rK/app-release.apk | 1.0.21 / code 1021 | 3160cf7d04efe3ca1617d00d07c27a73510fef915b1cc7c1b724f50909aabd7e |
| windows/x64/1.0.20-20261113-7kRqh1/CloudMeet-1.0.20-x64.msi | 1.0.20 | af886934fe3e47d008f59f88051785c42c5a692420183eac3973cf87f8b6def6 |
| windows/x64/1.0.21-cloudmeet-clients-zj3lBy/CloudMeet-1.0.21-x64.msi | 1.0.21 | 630b5bbfd4d0858defb4943d340b8c473b6a360975a5f582a15338633af56c68 |
| windows/x64/1.0.21-cloudmeet-clients-zSQ3rK/CloudMeet-1.0.21-x64.msi | 1.0.21 | f0c3d0e8b60276f07063f9afec4afd789a37b74f7555cbf38385b1fa48e7eb18 |

Additional workspace output inspection: jm's current APK is code 1021 and identical to the zj3lBy delivery. Electron unified output MSI versions range from 1.0.0 to 1.0.21; private-vpn MSI is 1.0.21 and vendor OpenVPN is not the CloudMeet product. Intermediate wix/cloudmeet.msi reports 1.0.21.0 (same Windows Installer first-three-field comparison, not a higher final CloudMeet delivery version).

## Pure preview, not allocation

At r1: server 11248.0.1+r1, client 1.0.21+r1, Android 10211, MSI 1.0.22, PE 1.0.22.0. Pure derivation reads policy without a ledger. Actual final-package versions/signatures and coverage upgrades remain unverified.

Auxiliary verification: revision tests 11/11, Node client tools 30/30, WSL Python 94/95 (only the pre-existing protected output/assemble-11248.0.1.sh inventory failure). Bash syntax, input hashes, workflow mirror bytes and diff checks pass. No product compilation or cloud workflow execution occurred.
