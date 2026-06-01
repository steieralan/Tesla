# Tesla Project Notes

## Tesla Account MFA
- Tesla account has MFA enabled (TOTP)
- The authenticator app originally used is unknown / no longer accessible
- **Backup passcodes are stored in the user's iPhone Notes app**
- When re-authenticating (running `auth.py`), prompt the user to look up the backup code in Notes

## Scheduling
- The GitHub Actions workflow's cron schedule was REMOVED — `monitor.yml` only has `workflow_dispatch`.
- The actual schedule is managed externally on **cron-job.org**.
- It triggers `https://api.github.com/repos/steieralan/Tesla/actions/workflows/monitor.yml/dispatches` every 5 minutes.
- Timezone is set to America/New_York.
- To adjust frequency or active hours, edit it at https://cron-job.org (look for the "Tesla" cronjob).
