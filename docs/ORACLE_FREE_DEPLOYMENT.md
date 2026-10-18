# FinSight: free Oracle deployment

Prepared 15 October 2026. Hosting is not live yet. The owner must finish Oracle
signup and provision a free VM before remote installation can proceed.

## 1. Account and server

Sign up at https://www.oracle.com/cloud/free/. Complete identity/card verification
yourself. Do not send passwords, card details, OTPs or private SSH keys in chat.
Keep the account on the free tier; do not upgrade to Pay As You Go for this demo.

Create an Ubuntu 24.04 ARM64 VM with shape `VM.Standard.A1.Flex`, 2 OCPUs,
up to 12 GB RAM, and a 50 GB boot disk, in the tenancy's home region. Confirm the
account's Always Free entitlement before creation. Do not use a paid marketplace
image, managed database, NAT gateway or load balancer. Use a public subnet with an
internet gateway and a public IP for this one-server deployment.

Oracle's current documentation lists 1,500 OCPU-hours and 9,000 GB-hours per month
(2 OCPUs / 12 GB for Always Free tenancies), 200 GB combined boot/block storage,
and five volume backups. The temporary trial credit is not the hosting plan.
If free capacity is unavailable, wait or try another availability domain in the
home region; do not purchase a different shape to work around it.

Oracle may reclaim idle instances. Keep a separate backup of data you need.
There is no uptime guarantee for this free demo.

Sources:
- https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- https://www.oracle.com/cloud/free/faq/

Save the SSH private key on your computer. The public IP, SSH username (normally
`ubuntu`), and local private-key file path are sufficient for the next deployment
step; do not paste the key contents.

## 2. Free hostname and networking

Use an existing domain or register an available free subdomain at
https://www.duckdns.org/. Set its IPv4 record to the VM's public IPv4. Only set
an IPv6 record if IPv6 is actually configured and reachable. No DuckDNS token
needs to be placed in this project for a manually configured address.

Allow TCP 80 and 443 from the internet in the Oracle network security group or
subnet security list. Allow TCP 22 only from your administrative public IP where
practical. Make corresponding rules in the VM's host firewall while preserving
SSH access. Do not expose 5432, 8000 or 5173. Docker publishes only 80 and 443;
review Docker's firewall integration rather than relying on UFW alone.

DNS must resolve correctly and both web ports must be reachable before Caddy can
obtain an HTTPS certificate. Caddy stores certificates in its persistent volume.

## 3. Transfer the source-only archive

`deploy/package.py` produces `output/deployment/finsight-deploy.tar.gz` from an
explicit list of application and deployment sources. It excludes local `.env`
files, uploaded workbooks, runtime output, logs, node_modules and Python caches.
It includes the saved model artifacts. Re-run it after changing application code:

```text
python deploy/package.py
```

Transfer the archive over SSH using `scp` (replace the placeholders). On Windows,
run this from the project root; keep your private-key path quoted:

```text
scp -i "PATH_TO_PRIVATE_KEY" output/deployment/finsight-deploy.tar.gz ubuntu@SERVER_IP:~/
ssh -i "PATH_TO_PRIVATE_KEY" ubuntu@SERVER_IP
```

On a fresh server, extract into a new folder, not over an existing deployment:

```sh
mkdir -p ~/finsight
tar -xzf ~/finsight-deploy.tar.gz -C ~/finsight
cd ~/finsight
```

The deployment starts with a fresh database. Existing Windows database records
contain absolute upload paths and must not be imported without an explicit path
migration and transfer of the corresponding files.

## 4. Install Docker and configure FinSight

Install Docker Engine and the Compose plugin using Docker's Ubuntu instructions:
https://docs.docker.com/engine/install/ubuntu/

Use the official apt repository procedure, including the ARM64 architecture.
After installation, `sudo docker version` and `sudo docker compose version` must
work. No Docker installation is required on your Windows computer.

From `~/finsight`, create new deployment-only credentials:

```sh
python3 deploy/configure.py YOUR_NAME.duckdns.org
sudo sh deploy/start.sh
```

The configuration script validates the hostname, writes a mode-0600 `deploy/.env`,
and refuses to overwrite existing secrets. Do not regenerate the database password
after initialization; changing the environment alone does not change PostgreSQL's
stored password. The example file is documentation, not a usable configuration.

The start script validates Compose, builds both images, runs a saved-model/SHAP
preflight, validates Caddy configuration, and starts services. On a small VM the
first dependency/image build can take several minutes. API and worker run as an
unprivileged user with the same `/data` volume. PostgreSQL has its own volume.
Frontend/API traffic stays on one HTTPS origin, preserving session cookies.

The Python image uses binary wheels only. If an ARM64 dependency lacks a compatible
wheel, the build stops; do not remove pins or replace model artifacts casually.
The ARM64 build and ML runtime must be verified on the actual server. There is no
claim that a successful Windows frontend build verifies these dependencies.

Optional password-reset mail is disabled until SMTP fields are filled in
`deploy/.env`. Use a verified sender and a relay supporting STARTTLS. After editing,
run `sudo docker compose --env-file deploy/.env up -d`. Keep SMTP passwords private;
use single-quoted dotenv values if they contain `$` or other interpolation syntax.

## 5. Launch verification

Run commands from `~/finsight`:

```sh
sudo docker compose --env-file deploy/.env ps
sudo docker compose --env-file deploy/.env logs --tail=100 worker
curl --fail https://YOUR_NAME.duckdns.org/api/health
```

Look for `FinSight worker ready` in worker logs. The API container health check
tests HTTP and PostgreSQL, but cannot establish that a workbook completes.

In the browser:
1. Open `https://YOUR_NAME.duckdns.org/register`, register and create a workspace.
2. Refresh `/app` directly to check client-side routing.
3. Upload a non-sensitive sample workbook and check preview/confirmation.
4. Wait for completion; check rules, ML, SHAP and PDF download.
5. Sign out and back in; confirm the analysis remains available.
6. Restart the stack and confirm the same saved report still downloads.

```sh
sudo docker compose --env-file deploy/.env restart
```

Processing is intentionally serialized by the application. This setup does not
increase analysis concurrency or make the project suitable for sensitive public
production use without further review.

## 6. Backups and updates

Keep database and artifacts together. For a consistent demo backup, stop public
writes and the worker, dump the database and archive the artifact volume. This
causes planned downtime. Run in a shell from `~/finsight`:

```sh
umask 077
backup_dir="deploy/backups/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup_dir"
sudo docker compose --env-file deploy/.env stop web worker api
sudo docker compose --env-file deploy/.env exec -T db pg_dump -U finsight -d finsight -Fc > "$backup_dir/database.dump"
sudo docker compose --env-file deploy/.env run --rm --no-deps -T api tar -czf - -C /data . > "$backup_dir/artifacts.tar.gz"
sudo docker compose --env-file deploy/.env up -d
```

Check both backup commands succeeded and files are nonempty before relying on the
backup. Restart services even if a backup step fails. Download backups to a private
location outside the VM. Keep a secure separate copy of `deploy/.env`. A restore
requires both database and artifacts at the original `/data` paths; test restoration
in an isolated environment before relying on it.

Before updating, make a backup. Preserve `deploy/.env` and Docker volumes, transfer
the revised sources, then run `sudo sh deploy/start.sh`. Schema-changing releases
require explicit migrations; `create_all` does not alter existing tables.

Do not use `docker compose down -v` or volume-pruning commands: they delete saved
data. Ordinary container restarts and rebuilds preserve named volumes. A VM deletion
can remove storage; named volumes are not an off-server backup.

## Current validation boundary

Local checks performed on 15 October 2026:
- `npm run build` passed.
- Compose YAML parsed; API/worker shared mounts, private ports, startup dependencies
  and secure-cookie settings were inspected successfully.
- Archive inspection passed: 117 source/build files, four model artifacts, no local
  credentials or uploaded client workbooks. The intentionally public
  `frontend/public/data/FinSight_Template.xlsx` is retained.
- Included Python source compiled successfully.
- Configuration generation rejected six malformed hostnames, generated a fresh
  config and refused to replace an existing config.
- The local backend runtime check could not complete because the available Python
  environment lacks `shap`; this does not validate the Linux image.

Docker is not installed on the preparation computer. Docker Compose schema/runtime
validation, the ARM64 image build, certificate issuance, hosted login and a real
queued analysis remain server-side checks. The app is not deployed merely because
these files exist.
