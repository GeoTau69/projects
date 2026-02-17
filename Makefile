# Projektový workspace — hlavní Makefile
.PHONY: docs validate new-project list

# Regeneruje root CLAUDE.md z project.yaml souborů
docs:
	python3 _meta/generate-docs.py

# Validuje izolaci všech projektů
validate:
	python3 _meta/validate-isolation.py

# Vytvoří nový projekt: make new-project NAME=muj-projekt
new-project:
	@test -n "$(NAME)" || (echo "Použití: make new-project NAME=nazev-projektu" && exit 1)
	bash _meta/new-project.sh $(NAME)

# Vypíše všechny projekty
list:
	@echo "Projekty:"
	@for d in */; do \
		if [ -f "$$d/project.yaml" ]; then \
			status=$$(grep 'status:' "$$d/project.yaml" | head -1 | awk '{print $$2}' | tr -d '"'); \
			echo "  $$d — $$status"; \
		fi; \
	done
