#!/bin/bash
# One deploy script for everything under /opt/mikhail-codes: the Flask
# app (books.mikhail.codes) and the Jekyll build (mikhail.codes). Run
# from the VM: bash /opt/mikhail-codes/deploy.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "== books.mikhail.codes (Flask) =="
git pull origin main
./venv/bin/pip install -q -r requirements-render.txt
systemctl restart mikhail-codes
echo "restarted mikhail-codes.service"

echo
echo "== mikhail.codes (Jekyll) =="
cd site
git pull origin master
bundle install --quiet
bundle exec jekyll build
echo "rebuilt site/_site"

echo
echo "done."
