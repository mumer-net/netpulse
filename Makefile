# Recipes start with ">" instead of a tab, so copy-paste can't break them.
.RECIPEPREFIX = >
LAB := netpulse.clab.yml
.PHONY: deploy redeploy destroy status chaos chaos-smoke chaos-dry handoff test clear-alerts set-user

deploy:
> sudo containerlab deploy -t $(LAB)
redeploy:
> sudo containerlab deploy -t $(LAB) --reconfigure
destroy:
> sudo containerlab destroy -t $(LAB) --cleanup
status:
> sudo containerlab inspect -t $(LAB)
chaos:
> python3 tools/chaos.py --runs 20
chaos-smoke:
> python3 tools/chaos.py --scenarios link_down --runs 2
chaos-dry:
> python3 tools/chaos.py --runs 2 --dry-run
handoff:
> python3 tools/handoff.py --hours 8
test:
> ruff check tools tests && pytest -q
clear-alerts:
> sudo rm -f results/alerts.jsonl
# make set-user GH=your-github-username   (fills every YOUR_USER placeholder)
set-user:
> test -n "$(GH)" || (echo "usage: make set-user GH=<github-username>" && exit 1)
> grep -rl YOUR_USER --exclude=Makefile --exclude-dir=.git --exclude-dir=.venv . | xargs sed -i "s/YOUR_USER/$(GH)/g"
> echo "Replaced YOUR_USER with $(GH)"
