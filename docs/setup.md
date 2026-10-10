# Setup: accounts, keys and where each one goes

For the owner. Nothing here costs money. Never paste a key into a chat, an issue, a commit or a log.

## The rule of thumb

A key goes wherever code that uses it runs:

| Where code runs | What it does | Where its keys go |
|---|---|---|
| **GitHub Actions** | The scheduled collectors and mining jobs: the system itself | Repo → **Settings → Secrets and variables → Actions → New repository secret** |
| **Claude Code cloud sessions** | Building and testing the code against the live APIs, and reading results back to you | The session's cloud environment: **the environment menu in the session's title bar → Edit → Network secrets** (labelled "API credentials" in older app versions; if neither is offered, add it as an environment variable). A *new* session picks it up; a running one doesn't. |
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

## Creating the R2 token

The bucket `moria` already exists. It is private, Standard storage, located in Eastern North America near the
GitHub Actions runners, and was created on 2026-10-10.

1. Cloudflare dashboard → **R2 Object Storage** → **Manage API tokens** → **Create API token**.
2. Permissions: **Object Read & Write**.
3. Scope: **Apply to specific buckets only** → `moria`.
4. Create it, then copy the **Access Key ID** and the **Secret Access Key** into GitHub Actions secrets and the Claude
   Code environment, under the names above. Add your account ID as `R2_ACCOUNT_ID` in both places as well.

Don't enable public access on the bucket. Reports are shared another way.

## Checklist

- [ ] `OPENALEX_API_KEY` in GitHub Actions secrets
- [ ] `OPENALEX_API_KEY` in the Claude Code environment
- [ ] `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID` and `R2_SECRET_ACCESS_KEY` in GitHub Actions secrets
- [ ] The same three in the Claude Code environment
- [ ] Start a new Claude Code session after adding environment secrets

On day 1 the first session checks each key with one cheap call and reports which ones answered. It never prints the
values.
