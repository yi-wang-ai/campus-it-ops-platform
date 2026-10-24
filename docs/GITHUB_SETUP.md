# Publish on GitHub

## 1. Create an empty repository

Open <https://github.com/new> and select your GitHub account. Suggested repository name: **`campus-it-ops-platform`**. Choose **Public** only when you have reviewed the source for secrets. Do **not** initialize another README, license or `.gitignore`; all are included here.

## 2. Review before publishing

- Ensure `.env`, `data/`, local VM IP addresses and `ansible/inventory.ini` are excluded.
- Run `git status` and `git grep -n -E '(password|TOKEN=|PRIVATE KEY)'` on **tracked content** and inspect results. Placeholder names and lab docs are expected; real secrets must never appear.
- Run the test commands from README. Replace the simulated screenshot with real lab evidence later.
- Confirm that you understand the difference between your original integration code and upstream Zabbix/Ansible.

## 3. Push the extracted files

```bash
cd campus-it-ops-platform
git init
git branch -M main
git add .
git commit -m "feat: add incident API, Zabbix webhook and gated Ansible recovery"
git remote add origin https://github.com/YOUR_USERNAME/campus-it-ops-platform.git
git push -u origin main
```

Use your own verified GitHub username in the URL. GitHub authentication may require a browser flow or SSH key; never paste tokens into README files.

## 4. Make the GitHub profile compelling

- Repository description: `Zabbix + FastAPI + Ansible | auditable incident workflow, safe remediation and recovery verification`
- Topics: `python`, `fastapi`, `zabbix`, `ansible`, `linux`, `devops`, `monitoring`, `incident-management`, `docker`.
- Pin the repository to your profile.
- Check **Actions**: do not claim CI passed until GitHub shows a real successful run.
- Add real evidence: deployed Zabbix screenshot, Ansible output with private data redacted, and short demonstration recording.
- Issue/PR templates are supplied so future work is traceable.

## 5. Suggested release

Tag `v1.0.0-lab` **only after** verifying local tests and reviewing scope notes. Mark actual live Zabbix/SSH demo as pending until performed. Do not invent a company, collaborator, deployment uptime or performance benchmark.
