# Prompt d'audit — TestScribe (P3)

> À coller dans Claude Code, à la racine du repo, après un `/clear`.
> CLAUDE.md doit déjà être présent à la racine (il sera lu automatiquement).

---

Le projet est en statut COMPLETE et validé en conditions réelles (144/144 tests, demo 30/30, dashboard Flask opérationnel). Je ne veux AUCUNE réécriture, refactor ou "amélioration" sans validation explicite. Ta mission est un AUDIT en lecture, pas une intervention.

Objectif : vérifier qu'on n'est passé à côté de rien, en particulier sur les 3 bugs documentés comme preuve de process QA et sur le pipeline RAG/ChromaDB. Rapport structuré (✅ solide / ⚠️ à surveiller / 🔧 correctif proposé — jamais appliqué sans mon accord).

## 1. Suite de tests
- Lance `python -m pytest -v`, confirme 144/144 verts, relève le temps d'exécution.
- Relance une deuxième fois pour détecter une flakiness éventuelle (le pipeline RAG/ChromaDB est le point le plus à risque ici).

## 2. Fallback déterministe (4 agents)
- Pour ReportEnricher, SeverityScorer, PatternClassifier, ComplianceTagger : confirme un fallback rule-based fonctionnel et la suite verte sans clé API.

## 3. Intégrité des 3 bugs documentés (portfolio evidence — NE PAS CORRIGER, juste vérifier)
- Confirme que le test couvrant le bug de lookbehind regex sur `ALWAYS_REPRO` est toujours présent et vert.
- Confirme que le seuil critique est toujours à **8.0** (pas revenu à 8.5 par erreur, ex. lors d'un merge ou d'une dépendance).
- Confirme que `IEC_CLASS_B_RE` a toujours sa version corrigée et que le test de régression associé (faux positifs Class B sur bugs cosmétiques) est vert.

## 4. RAG / ChromaDB
- Vérifie que la persistence ChromaDB fonctionne toujours et que les embeddings TF-IDF ne dépendent d'aucun appel réseau.
- Ne scanne PAS le contenu du dossier de persistence ChromaDB en détail (token waste) — vérifie juste que le pipeline s'initialise et répond correctement sur un cas de test simple.

## 5. Dashboard Flask
- Vérifie que le dashboard démarre sans erreur (`flask run` ou équivalent) et répond sur sa route principale.

## 6. Docker & CI
- Vérifie que `docker-compose.yml` build toujours correctement.
- Vérifie que le workflow CI est cohérent avec la commande de test locale (`python -m pytest`).

## 7. Dépendances & secrets
- `pip list --outdated`.
- Grep pour clés API/tokens committés par erreur.
- Vérifie `.gitignore` (`.venv/`, ChromaDB storage, sorties demo).

## 8. Cohérence documentaire
- Compare le README (144/144, demo 30/30, description des 4 agents, IEC 62304/PSD2) avec l'état réel.
- Vérifie que les ADRs (notamment le choix TF-IDF vs embeddings neuronaux) correspondent toujours à l'implémentation.

## 9. Qualité résiduelle
- `TODO`/`FIXME`, code mort, commentaires obsolètes.

## Livrable attendu

Rapport unique en anglais professionnel, ✅/⚠️/🔧 par section. Une attention particulière sur la section 3 (les 3 bugs) : c'est la partie la plus sensible à protéger pour l'entretien. Propose sans appliquer. Si tout est vert, confirme-le simplement.
