# Setup: accounts, keys and where each one goes

For the owner. Nothing here costs money. Never paste a key into a chat, an issue, a commit or a log.

## The rule of thumb

A key goes wherever code that uses it runs:

| Where code runs | What it does | Where its keys go |
|---|---|---|
| **GitHub Actions** | The scheduled collectors and mining jobs: the system itself | Repo → **Settings → Secrets and variables → Actions → New repository secret** |
| **Claude Code cloud sessions** | Building and testing the code against the live APIs, and reading results back to you | The session's cloud environment: **the environment menu in the session's title bar → Edit → Environment variables**, one `NAME=value` per line. **Not Network secrets** (see below). A *new* session picks them up; a running one doesn't. |
| **Kaggle or Colab notebooks** (later, optional) | One-off GPU bursts such as the embedding backfill | The notebook's own secret store (Kaggle: Add-ons → Secrets; Colab: the key icon). Add them only when we first run one. |

So **the OpenAlex key goes in both GitHub Actions and the Claude Code environment,** under the same name. Actions runs
the daily collection; Claude Code sessions use it to build and test the OpenAlex adapter. The same goes for the R2
keys below.

## The names Moria will read

Use exactly these names in every place.

| Name | Where you get it | Used by |
|---|---|---|
| `OPENALEX_API_KEY` | Your OpenAlex account (free) | The OpenAlex collector |
| `R2_ACCOUNT_ID` | Cloudflare dashboard: your account ID, also shown in the R2 S3 endpoint `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` | Every job that reads or writes the bucket |
| `R2_ACCESS_KEY_ID` | The R2 API token you create below | The same |
| `R2_SECRET_ACCESS_KEY` | The same token. It is shown **once**, so copy it straight into the secret stores. | The same |
| `GCP_PROJECT_ID` | Your Google Cloud project with no billing account (below) | The patent counts on BigQuery |
| `GCP_SA_KEY` | The JSON key of a service account with BigQuery Job User (below) | The same |

**Why environment variables, not Network secrets.** A network secret makes the session's proxy add the key to the
headers of web requests. R2 doesn't take keys that way: it speaks the S3 protocol, where the secret key never travels
and the code uses it to sign each request. A header can't do that signing. The code also reads all four names from the
environment. The trade-off is that a session can read its environment variables, which is why the R2 token is
scoped to the `moria` bucket alone.

## Creating the R2 token

The bucket `moria` already exists. It is private, Standard storage, located in Eastern North America near the
GitHub Actions runners, and was created on 2026-10-10.

1. Cloudflare dashboard → **R2 Object Storage** → **Manage API tokens** → **Create API token**.
2. Permissions: **Object Read & Write**.
3. Scope: **Apply to specific buckets only** → `moria`.
4. Create it, then copy the **Access Key ID** and the **Secret Access Key** into GitHub Actions secrets and the Claude
   Code environment, under the names above. Add your account ID as `R2_ACCOUNT_ID` in both places as well.

Don't enable public access on the bucket. Reports are shared another way.

## BigQuery, for the patent counts (not set up yet)

Moria counts patent families by CPC subclass from Google's public patent data on BigQuery (D-011). The data is free,
and so are the first 1 TiB of queries each month, but every query needs a Google Cloud project to run in. Use a
**BigQuery sandbox**: a project with **no billing account**. Then nothing can ever be billed, whatever happens.

1. [console.cloud.google.com](https://console.cloud.google.com) → create a project, for example `moria-patents`.
   **Don't link a billing account.** Note its project id.
2. Open **BigQuery** in that project once, so the BigQuery API is on (the page shows a sandbox banner).
3. **IAM & Admin → Service accounts → Create service account:** `moria-bigquery`. Grant it the role
   **BigQuery Job User** on the project, and nothing else. The public patent data needs no further role.
4. Open the service account → **Keys → Add key → Create new key → JSON**. The file downloads once.
5. Add two **GitHub Actions secrets** (the counts run on Actions, so the Claude Code environment doesn't need them):
   - `GCP_PROJECT_ID`: the project id;
   - `GCP_SA_KEY`: the **whole content** of the JSON file, pasted as it is. Then delete the downloaded file.
6. Run **Actions → collect-source → Run workflow** with source `patent_cpc_counts`. It is a **dry run**: it records how
   many bytes the query would scan, in its manifest, and collects nothing. I then report the estimate, and you say
   whether to switch the dry run off.

The key can only run queries in a project that can't be billed. A keyless alternative, workload identity federation
from GitHub, is more secure but takes about ten more steps; it can replace the key later.

## Checklist

- [ ] `OPENALEX_API_KEY` in GitHub Actions secrets
- [ ] `OPENALEX_API_KEY` in the Claude Code environment, as an environment variable
- [ ] `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID` and `R2_SECRET_ACCESS_KEY` in GitHub Actions secrets
- [ ] The same three in the Claude Code environment, as environment variables
- [ ] Start a new Claude Code session after adding the environment variables
- [ ] Later, for the patent counts: `GCP_PROJECT_ID` and `GCP_SA_KEY` in GitHub Actions secrets (above)

On day 1 the first session checks each key with one cheap call and reports which ones answered. It never prints the
values.
