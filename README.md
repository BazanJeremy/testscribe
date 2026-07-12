# TestScribe

**Enrichissement de bug reports assisté par IA : *« button doesn't work »* → rapport de défaut structuré — sévérité CVSS-lite, classification IEC 62304, détection sémantique de doublons — en moins de 100 ms.**

[![CI](https://github.com/BazanJeremy/testscribe/actions/workflows/ci.yml/badge.svg)](https://github.com/BazanJeremy/testscribe/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/tests-144%20passing-brightgreen?logo=pytest)](tests/)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue?logo=python)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

> 🇬🇧 [English version](README.en.md)

**L'IA propose, le QA arbitre.** TestScribe est le maillon aval d'un flux qualité outillé par IA : il pré-qualifie les défauts entrants, la décision reste humaine. En aval, les rapports enrichis servent de cas d'usage d'évaluation pour [EvalForge](https://github.com/BazanJeremy/EvalForge) — interopérabilité souple, aucun couplage à l'exécution.

---

## Le problème

Toute équipe QA reçoit chaque semaine des signalements de ce type :

```
"button doesn't work"
"page crashes"
"search not working sometimes"
```

Inexploitables en l'état. Reconstituer un ticket de défaut structuré — titre, étapes de reproduction, sévérité, doublons éventuels — coûte 10 à 30 minutes par signalement. Et en secteur régulé (medtech, fintech), la qualification réglementaire arrive souvent trop tard dans le cycle.

TestScribe automatise cette **pré-qualification**. Le jugement, lui, n'est pas automatisé.

---

## L'approche

```
Rapport brut  (texte libre · JSON · CSV · POST /api/enrich)
      │   RawReport — validation Pydantic v2
      ▼
Orchestrateur (src/core/orchestrator.py)
      ├── ReportEnricher      titre normalisé · steps Given/When/Then · environnement
      ├── SeverityScorer      score CVSS-lite 0–10 · priorité
      ├── PatternClassifier   RAG ChromaDB + TF-IDF · 9 patterns · doublons
      └── ComplianceTagger    IEC 62304 (medtech) · PSD2 / DORA (fintech)
      │   EnrichedReport — validation Pydantic v2
      ▼
Dashboard Flask — revue et arbitrage par le QA
```

Chaque agent fonctionne en deux modes :

- **Mode LLM** — `claude-sonnet-4-6` (SDK Anthropic), sortie JSON validée par Pydantic ;
- **Fallback déterministe** — règles explicites, sans clé API : la CI tourne verte, coût zéro, résultats reproductibles.

Ce fallback n'est pas un pis-aller, c'est une exigence d'architecture : un outil qualité dont la suite de tests dépend d'un service externe n'est pas un outil qualité.

---

## Exemple concret

```
Entrée brute :  "The infusion pump alarm doesn't sound when the line is blocked."

Sortie :
  Titre    : Infusion pump alarm silent on IV occlusion
  Pattern  : SAFETY_CRITICAL
  Steps    : Given the user has access to alarm-subsystem
             When The occlusion alarm does not sound when IV line is blocked
             Then the observed behaviour differs from expected
  CVSS-lite : 9.0 / 10  →  CRITICAL
  IEC 62304 : Classe C  (change control requis, impact SOUP : non)
  Doublons  : RAW-001 (similarité 0.94)  →  probabilité de doublon : 89 %
```

---

## Le rôle du QA : l'IA propose, le QA arbitre

Chaque sortie de TestScribe est une **proposition**, jamais une décision :

| Sortie de TestScribe | Statut | La décision qui reste humaine |
|---|---|---|
| Score CVSS-lite + priorité | pré-classement | la sévérité finale du ticket |
| Steps Given/When/Then | proposition de reproduction | la reproduction effective du bug |
| Probabilité de doublon | signal | fusionner ou non les tickets |
| Tags IEC 62304 / PSD2-DORA | pré-qualification | la position réglementaire — jamais soumise telle quelle à un audit |

**Traçabilité intégrale** : chaque rapport enrichi porte un champ `enriched_by` (`claude-sonnet-4-6` ou `rule-based-fallback`) et un `confidence_score`. Le QA sait toujours *qui* a produit *quoi*, avec quelle confiance. L'exact opposé d'une boîte noire.

### Ce que TestScribe ne fait pas

- Il ne décide pas de la sévérité finale.
- Il ne clôt aucun ticket.
- Il ne remplace pas la reproduction manuelle du bug.
- Il ne délivre aucun avis de conformité réglementaire.
- Il ne génère pas de cas de test.

TestScribe supprime le temps de rédaction et de pré-qualification — pas le jugement.

---

## L'outil IA est lui-même sous contrôle QA

Trois bugs réels du pipeline ont été attrapés par la suite de tests pendant le développement — process complet à chaque fois : *test caught it → analyzed → fixed → regression-tested*.

| Bug | Test qui l'a attrapé | Correctif |
|---|---|---|
| `"not always"` scoré comme reproductible `always` | `test_intermittent_is_sometimes` | lookbehind négatif : `(?<!not )\balways\b` |
| Alarme de pompe à perfusion scorée `high` au lieu de `critical` | `test_alarm_bug_scores_critical` | seuil critique abaissé 8.5 → 8.0 |
| Bug cosmétique UI classé IEC 62304 classe B | `test_class_a_no_change_control` | regex classe B resserrée ; classe A sans change control |

144 tests (121 unitaires dont property-based avec Hypothesis, 23 d'intégration API), CI en 5 jobs sans clé API, décisions d'architecture tracées en ADRs. Le niveau d'exigence qu'on applique à un logiciel régulé, appliqué à l'outil IA lui-même.

---

## Démo locale

```bash
git clone https://github.com/BazanJeremy/testscribe.git
cd testscribe
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt

# Démo — 30 rapports seed, aucune clé API requise
python demo.py
python demo.py --sector medtech --verbose
python demo.py --sector fintech --json-out enriched.json

# Tests
python -m pytest

# Dashboard
python src/api/app.py
# → http://localhost:5000
```

Avec clé API (optionnel — fallback automatique sans) :

```powershell
$env:ANTHROPIC_API_KEY="sk-ant-..."
python src/api/app.py
```

Docker :

```bash
docker-compose up
# → http://localhost:5000
```

---

## Stack technique

```
Python 3.12+      Pydantic v2      Flask 3.x
SDK Anthropic     ChromaDB         scikit-learn (TF-IDF)
pytest            Hypothesis       Allure
GitHub Actions    Docker
```

---

## Limites explicites

- Les heuristiques du fallback sont calibrées sur 30 rapports seed — pas sur un corpus industriel.
- TF-IDF capte la similarité lexicale, pas la sémantique fine. Choix assumé ([ADR-002](docs/ADR-002-embeddings-choice.md)) : zéro dépendance réseau en CI, déterminisme ; la montée vers sentence-transformers est documentée.
- Les tags de conformité sont une aide à la qualification, pas un avis réglementaire.
- Le mode fallback produit des sorties plus pauvres que le mode LLM (règles à mots-clés, pas de reformulation).
- Corpus, patterns et sorties en anglais uniquement.

---

## Décisions d'architecture

- **[ADR-001](docs/ADR-001-chromadb-vs-faiss.md)** — ChromaDB plutôt que FAISS : API simple, persistance, filtrage par métadonnées pour l'isolation par secteur
- **[ADR-002](docs/ADR-002-embeddings-choice.md)** — TF-IDF par défaut, sentence-transformers en option : CI sans réseau, neural disponible en production
- **[ADR-003](docs/ADR-003-cvss-lite-scoring.md)** — CVSS-lite adapté au QA : 4 dimensions calibrées sur les exigences de sécurité medtech

---

## Projets associés

Ces outils partagent les mêmes principes : **le déterministe d'abord, l'IA là où elle apporte — le QA reste l'arbitre.** Tous tournent en local, aucune clé API requise.

| Projet | Focus |
|---|---|
| [EvalForge](https://github.com/BazanJeremy/EvalForge) | Évaluation de LLM & calibration du juge |
| [ReleaseGuard](https://github.com/BazanJeremy/ReleaseGuard) | Verrou de release GO/NO-GO explicable |
| [FlakySense](https://github.com/BazanJeremy/flakysense) | Diagnostic statistique des tests flaky |
| [Anomaly Sentinel](https://github.com/BazanJeremy/anomaly-sentinel) | Tester les IA de détection d'anomalies (medtech · fintech) |
| [TestScribe](https://github.com/BazanJeremy/testscribe) **← ce repo** | Enrichissement de bug reports assisté par IA |
| [SkyGuard](https://github.com/BazanJeremy/skyguard) | Quality gate sécurité pour systèmes critiques avioniques |

## Auteur

**Jérémy Bazan** — QA Engineer · AI Test Engineering
ISTQB Foundation v4 · MCP en production
[LinkedIn](https://www.linkedin.com/in/jeremy-bazan/) · [GitHub](https://github.com/BazanJeremy)
Lyon, France → Suisse romande / full remote
