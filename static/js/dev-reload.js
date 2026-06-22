(function () {
    const intervalMs = 1000;
    let currentVersion = null;

    async function checkStaticVersion() {
        try {
            const response = await fetch('/api/static-version', { cache: 'no-store' });
            const data = await response.json();

            if (currentVersion === null) {
                currentVersion = data.version;
                return;
            }

            if (data.version !== currentVersion) {
                window.location.reload();
            }
        } catch (error) {
            console.debug('Static reload check failed:', error);
        }
    }

    checkStaticVersion();
    setInterval(checkStaticVersion, intervalMs);
})();
