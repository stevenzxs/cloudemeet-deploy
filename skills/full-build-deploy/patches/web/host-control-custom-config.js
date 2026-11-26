// Append to the persistent Jitsi /config/custom-config.js after backend gates
// pass. configOverwrite filters this key on stable-11248. This flag controls
// presentation only; it never grants authority or replaces server validation.
(function () {
    if (config.cloudmeetHostTransferEnabled !== true) return;
    var buttons = config.customParticipantMenuButtons || [];
    if (buttons.some(function (button) { return button.id === 'cloudmeet-transfer-host'; })) return;
    config.customParticipantMenuButtons = buttons.concat([{
        id: 'cloudmeet-transfer-host',
        text: '设为主持人',
        icon: 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJjdXJyZW50Q29sb3IiIHN0cm9rZS13aWR0aD0iMiI+PHBhdGggZD0iTTMgN2w0IDQgNS03IDUgNyA0LTQtMiAxMkg1TDMgN3oiLz48L3N2Zz4='
    }]);
}());
