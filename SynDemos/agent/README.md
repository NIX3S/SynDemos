# Agent IA Autonome — Architecture v2

Agent autonome d'exécution (planning → exécution outillée → vérification →
auto-correction) piloté par un LLM local via Ollama, exposé en streaming SSE.

## Lancer le projet

```bash
pip install -r requirements.txt
cp .env.example .env   # puis adapter AGENT_WORKSPACE, modèles, etc.

# S'assurer qu'Ollama tourne et que le(s) modèle(s) sont installés :
ollama serve
ollama pull qwen3:8b

uvicorn api.main:app --reload --port 8000
```

```bash
curl -N -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Crée un script qui calcule les nombres premiers jusqu'\''à 100"}'
```

Chaque ligne reçue est un événement JSON (`{"type": "...", "data": ...}`).

## Arborescence

```
config.py                 Toute la config (env-driven), une seule source de vérité
schemas.py                 Contrats Pydantic partagés (requêtes, events, plan, todos)

llm/
  base.py                  Interface abstraite LLMProvider + StreamChunk (multi-provider, streaming)
  ollama_provider.py        Implémentation Ollama (chat + chat_stream, JSON mode, séparation thinking/content)
  registry.py                Sélection du provider actif

tools/
  registry.py               @tool decorator + schémas function-calling
  sandbox.py                  Sécurité : normalize_path (anti path-traversal) + validate_command
  fs_tools.py                  write_file, edit_file, read_file, list_dir
  shell_tool.py                 shell (whitelist commandes, timeout, groupe de process tuable)
  pdf_tools.py                   read_pdf, inspect_pdf (extraction de texte via pypdf)
  process_registry.py            Registre des process shell actifs par run_id, pour /stop

core/
  run_context.py            AgentContext : état complet d'un run (todos, messages, fichiers...)
  memory.py                   Mémoire conversationnelle courte (classe, plus de global mutable)
  checkpoints.py                Snapshots avant chaque écriture de fichier -> undo/rollback
  events.py                      emit() : valide/persiste/formate un événement SSE
  planner.py                      build_plan (JSON mode) + build_agent_messages
  tool_runner.py                   Exécution des tool_calls avec retry + tracking checkpoints
  verifier.py                       Vérification (exécution des .py créés) + boucle de fix streamée
  engine.py                          LA FSM : start -> plan -> EXEC -> VERIFY -> FIX -> DONE/STOPPED
  replay.py                           Relit le JSONL d'un run terminé

storage/
  runs.py                   Runs actifs/archivés + persistance JSONL pour le replay

api/
  main.py                  App FastAPI (déclenche l'enregistrement des outils)
  routes.py                  /ask /debug/{id} /stop/{id} /replay/{id} /checkpoints/{id} /undo/{id} /
```

## Streaming temps réel (thinking + content token par token)

`/ask` streame désormais, en plus des événements existants, les deltas de
génération du LLM au fur et à mesure qu'ils arrivent d'Ollama :

- `thinking_delta` : fragment de texte de réflexion (qwen3 et les modèles
  qui exposent un raisonnement via des balises `<think>...</think>`)
- `content_delta` : fragment de la réponse finale

Exemple de flux brut (`curl -N -X POST .../ask ...`) :
```
{"type":"start", ...}
{"type":"plan", ...}
{"type":"todo_update", ...}
{"type":"thinking_delta","data":{"text":"Je dois "}}
{"type":"thinking_delta","data":{"text":"d'abord créer "}}
{"type":"content_delta","data":{"text":"Je vais créer le fichier app.py."}}
{"type":"exec", ...}            <- résumé complet une fois le tour terminé
{"type":"tool_result", ...}
{"type":"checkpoint", ...}
{"type":"verify", ...}
{"type":"final", ...}
```

Le parsing thinking/content est fait token par token via un petit
automate (`llm/ollama_provider.py::_ThinkTagSplitter`) qui gère le cas
où une balise `<think>`/`</think>` est coupée en plein milieu entre deux
chunks réseau (cas réel et fréquent en streaming).

Ça fonctionne aussi avec `curl --no-buffer` pour voir les tokens
apparaître au fur et à mesure plutôt que tout d'un coup à la fin :
```bash
curl -N --no-buffer -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"prompt": "explique-moi ce code"}'
```

## Undo / Rollback des fichiers

Chaque `write_file`/`edit_file` réussi enregistre un **checkpoint**
(contenu avant/après) dans une pile par run, avant même que l'agent
passe à l'étape suivante.

```bash
# Voir l'historique des modifications de fichiers d'un run
curl http://localhost:8000/checkpoints/<run_id>

# Annuler la dernière modification
curl -X POST http://localhost:8000/undo/<run_id>

# Annuler les 3 dernières modifications d'un coup
curl -X POST http://localhost:8000/undo/<run_id> \
  -H "Content-Type: application/json" -d '{"steps": 3}'
```

`undo` restaure le contenu précédent du fichier sur disque, ou **supprime
le fichier** si le checkpoint indique qu'il n'existait pas avant cette
modification (création annulée). Chaque appel dépile une étape de plus —
appeler `/undo` répété revient en arrière pas à pas, comme un undo
classique d'éditeur.

## Arrêt immédiat (/stop) — y compris pendant le streaming ou un shell long

`POST /stop/{run_id}` fonctionne maintenant à trois niveaux, pour un
arrêt réellement immédiat plutôt qu'un arrêt "à la prochaine étape" :

1. Positionne `ctx.stop_requested`, vérifié à chaque token reçu pendant
   le streaming LLM (`thinking_delta`/`content_delta`) — pas seulement
   entre deux étapes de la FSM.
2. Si une commande `shell` est en train de tourner pour ce run, le
   process est **tué immédiatement** (`os.killpg` sur tout le groupe de
   processus, pas juste le shell parent — sinon un `python script.py`
   lancé par le shell continuerait à tourner en arrière-plan jusqu'à sa
   fin naturelle malgré le kill).
3. La boucle de correction (fix loop) vérifie aussi l'arrêt entre chaque
   tentative et pendant son propre streaming.

```bash
curl -X POST http://localhost:8000/stop/<run_id>
# {"ok": true, "process_killed": true}
```

## Lecture de PDF

Deux nouveaux outils disponibles pour le LLM (et utilisables directement
via les modules `tools.pdf_tools` si besoin) :

- `inspect_pdf(path)` : nombre de pages, métadonnées, présence d'une
  couche de texte (sinon c'est probablement un scan, et l'extraction ne
  renverra rien d'utile).
- `read_pdf(path, start_page, end_page)` : extraction de texte page par
  page, tronquée à 50 000 caractères pour ne pas saturer le contexte du
  LLM avec un document trop volumineux.

Basé sur `pypdf` (pure Python, déjà dans `requirements.txt`) plutôt que
sur des binaires système (`poppler-utils`), pour simplifier le
déploiement. Pour des PDF scannés sans couche texte, voir le skill
`pdf-reading` (OCR, rasterisation) si une extraction plus poussée est
nécessaire — hors scope de cet outil volontairement simple.

## Recherche web

Deux nouveaux outils, sans API tierce payante ni clé à configurer —
juste une requête HTTP directe + parsing HTML (`requests` + `bs4`,
déjà dans `requirements.txt`) :

- `web_search(query, max_results)` : interroge DuckDuckGo HTML
  (`html.duckduckgo.com`, pas besoin de JavaScript contrairement à
  google.com) et retourne pour chaque résultat un titre, un extrait
  (snippet) et une URL.
- `web_fetch(url)` : récupère et nettoie le contenu texte complet d'une
  page précise (retire nav/script/style/footer), typiquement une URL
  jugée prometteuse parmi les résultats de `web_search`. Contenu
  tronqué à 8000 caractères, avec un garde-fou anti-SSRF basique
  (refuse `file://`, IPs locales/privées, endpoint de métadonnées cloud).

**Pourquoi DuckDuckGo plutôt que Google directement** : Google rend ses
résultats de recherche via JavaScript côté client, donc une requête HTTP
simple sans navigateur ne récupère qu'une page quasi-vide. DuckDuckGo a
une version HTML statique pensée pour ce genre d'usage, sans blocage
agressif pour un usage raisonnable.

**Le LLM décide lui-même de relancer une recherche** : le snippet de
chaque résultat est la donnée clé pour ça — le prompt système de l'agent
(`core/planner.py::AGENT_SYSTEM_PROMPT`) lui demande explicitement de
juger la pertinence des extraits et de reformuler la requête si les
résultats sont vagues ou hors sujet, plutôt que de se contenter du
premier résultat faible. Concrètement : une recherche "tarte citron" qui
ne renvoie que des généralités peut être suivie d'une seconde recherche
"tarte citron meringuée" dans le même run — rien de spécial à faire côté
moteur, la FSM (`core/engine.py`) laisse déjà le LLM enchaîner autant
d'appels d'outils qu'il veut dans la limite de `AGENT_MAX_STEPS`, exactement
comme pour une séquence d'écriture de plusieurs fichiers.

```bash
curl -N -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Trouve-moi une recette de tarte au citron meringuée"}'
# -> web_search("tarte citron") jugé vague par le LLM
# -> web_search("tarte citron meringuée") relancé automatiquement
# -> réponse finale basée sur le second résultat
```

**Vérifier que tous les outils sont bien chargés** : `GET /tools` liste
les outils réellement enregistrés et exposés au LLM à cet instant. Utile
pour confirmer sans ambiguïté qu'un outil attendu (ex: `web_search`) est
bien là, plutôt que de le découvrir au milieu d'un run. La même liste
est aussi loguée au démarrage du serveur (`agent.startup`).

```bash
curl http://localhost:8000/tools
# {"count": 9, "tools": [{"name": "write_file", ...}, ..., {"name": "web_search", ...}]}
```

## Routage automatique de modèle selon le type de tâche

Le planner classe désormais chaque demande dans une catégorie
(`code`, `redaction`, `synthese`, `reflexion`) en même temps qu'il génère
le plan — un seul appel LLM, pas de coût supplémentaire. Le modèle utilisé
pour l'**exécution** (pas le planning, qui reste sur `AGENT_MODEL_PLANNER`)
est ensuite choisi automatiquement via le mapping `.env` :

```bash
AGENT_MODEL_CODE=qwen3:14b        # code : modèle fort, function-calling fiable
AGENT_MODEL_REDACTION=llama3.1:8b # rédaction : modèle à l'aise en texte naturel
AGENT_MODEL_SYNTHESE=llama3.1:8b  # résumé/extraction
AGENT_MODEL_REFLEXION=qwen3:14b   # analyse/raisonnement
```

Si une variable n'est pas définie, elle retombe sur `AGENT_MODEL_EXEC` —
donc un déploiement avec un seul modèle continue de fonctionner exactement
comme avant, sans aucune configuration supplémentaire à faire.

Le modèle réellement choisi est visible dans l'event `plan`
(`"model_used": "..."`) et via `/debug/{run_id}`. Si le client envoie
explicitement `{"model": "..."}` dans `/ask`, cet override garde toujours
la priorité sur le routage automatique — la classification du planner
est une aide par défaut, jamais une contrainte.

```bash
curl -N -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Rédige un email de relance client"}'
# -> task_category="redaction", model_used="llama3.1:8b" (si configuré)
```

## Commandes longues protégées (pip install, scripts python, etc.)

Un `pip install scikit-learn` ou un script qui entraîne un modèle peuvent
légitimement prendre plusieurs minutes — ce n'est pas un blocage à
interrompre. Les commandes commençant par `pip`/`pip3` **ou**
`python `/`python3 ` sont marquées **protégées** :

- Le timeout normal (`AGENT_SHELL_PIP_TIMEOUT` pour pip,
  `AGENT_SHELL_TIMEOUT` pour python) ne les tue jamais : l'attente
  continue indéfiniment jusqu'à la fin réelle du calcul ou de
  l'installation, comme le ferait un développeur qui laisse tourner un
  entraînement scikit-learn sans paniquer après 2 minutes.
- Un premier appel à `/stop/{run_id}` ne tue **pas** le process : il
  retourne `{"status": "confirmation_required", "command": "...", "running_for_seconds": ...}`
  pour signaler qu'un calcul est en cours.
- Il faut un second appel explicite avec confirmation pour vraiment
  l'interrompre :
  ```bash
  curl -X POST http://localhost:8000/stop/<run_id> \
    -H "Content-Type: application/json" -d '{"force": true}'
  # {"ok": true, "status": "killed", "command": "python3 train_model.py"}
  ```

Toute autre commande shell (`ls`, `find`, `pytest`, etc.) reste tuée
immédiatement sur simple `/stop`, sans confirmation.

**Impact sur la vérification automatique** : `core/verifier.py` exécute
chaque `.py` créé via ce même `shell()` protégé — donc un script qui fait
un vrai calcul long (ex: `from sklearn import ...` + entraînement) ira
au bout pendant `verify_code` aussi, sans être coupé. C'est voulu : sinon
la protection serait inutile pour exactement le cas d'usage qu'elle vise.

**Contrepartie à connaître** : si l'agent génère par erreur une vraie
boucle infinie (pas un calcul long, un bug), elle n'est plus coupée
automatiquement non plus — il faut alors un `/stop force=true` manuel
pour la débloquer. `/debug/{run_id}` permet de repérer un run dont
`step`/`state` ne progresse plus depuis longtemps si ce cas survient.

## Bugs corrigés par rapport à la version précédente

| # | Fichier d'origine | Bug | Correction |
|---|---|---|---|
| 1 | `context.py` | `field(default_factory=...)` au niveau module, hors dataclass → plantage à l'import | Tout déplacé proprement dans `AgentContext` (`core/run_context.py`) |
| 2 | `tools.py` `write_file` | `diff` jamais initialisé si le fichier est nouveau → `UnboundLocalError` | `diff` toujours calculé via `_diff(before, after)`, `before` peut être `None` |
| 3 | `tools.py` | `WORKSPACE` ré-importé de `configuration.py` puis **ré-écrasé en dur** juste après → toute la sécurité de chemin ignorait la vraie config | `WORKSPACE` vient uniquement de `config.py`, jamais réassigné ailleurs |
| 4 | `tools.py` `write_file` | `Path(path).name if path.endswith(".py")` tronquait les sous-dossiers pour tout fichier `.py` | Supprimé — la sécurité est uniquement assurée par `normalize_path` |
| 5 | `verifier.py` vs `executor.py` | Deux implémentations différentes de `verify_code`/`execute_all_python`, celle d'`executor.py` shadowait l'import et `verifier.py` n'était plus jamais réellement utilisé | Une seule implémentation dans `core/verifier.py`, utilisée par la FSM |
| 6 | `executor.py` FSM | Transition EXEC→VERIFY conditionnée à `plan.need_execution AND created_files` → si le planner se trompait sur `need_execution`, le code généré n'était jamais vérifié | Transition basée uniquement sur la présence de fichiers `.py` créés, indépendamment du plan |
| 7 | `executor.py` `shell` (via `tools.py`) | `timeout=None` pour `pip` → un `pip install` qui bloque ne s'arrête jamais | Timeout dédié et fini pour `pip` (`AGENT_SHELL_PIP_TIMEOUT`, 300s par défaut) |
| 8 | `llm.py` `build_plan` | `except: return plan vide` avalait toute erreur de parsing JSON sans distinction (Ollama down ? JSON mal formé ? Modèle qui bavarde ?) | Erreurs distinguées (`LLMProviderError` vs `JSONDecodeError`), visibles dans `plan.steps` |
| 9 | `llm.py` | Pas de `format: "json"` envoyé à Ollama → dépendance à un fallback regex fragile (`regex_tool` dans `executor.py`) | Mode JSON natif d'Ollama forcé pour le planner ; `regex_tool` supprimé |
| 10 | `api.py` | `/replay/{run_id}` appelle `replay_run` qui n'est **jamais importée** → `NameError` au premier appel | Importée et branchée dans `api/routes.py` |
| 11 | `api.py` | `/debug/{run_id}` ne cherche que dans `RUNS` → un run juste archivé devient introuvable | `RunStore.get()` cherche dans actifs **et** archivés |
| 12 | `executor.py` | `print("step0")`, `print("step 1")`... partout (debug oublié en prod) | Remplacés par `logging` standard, configurable, silencieux par défaut |
| 13 | `core/engine.py` (introduit dans une itération précédente de cette refonte) | La transition EXEC→VERIFY se déclenchait dès le **premier** fichier `.py` créé, même si le LLM avait encore d'autres tool_calls prévus dans son tour → une séquence multi-fichiers liés (ex: `utils.py` puis `main.py` qui l'importe) était interrompue après le premier fichier, le second n'était jamais créé | La transition n'a lieu que quand le LLM n'appelle plus aucun outil (tour terminé), pas après chaque tool_call individuel — testé avec un scénario à 2 fichiers interdépendants |
| 14 | `core/tool_runner.py` (introduit dans une itération précédente de cette refonte) | Ollama renvoie parfois `tool_call.function.arguments` sous une forme inattendue (liste, string JSON au lieu d'un dict déjà parsé) selon le modèle — le code appelait directement `.get(...)`/`**args` sans valider, ce qui faisait planter **tout le run** avec `'list' object has no attribute 'get'`, en pleine utilisation réelle avec Ollama | `_normalize_arguments()` valide et convertit la forme reçue (dict → tel quel, string JSON → parsée, tout le reste → dict vide + log d'erreur) avant tout usage ; un outil avec des arguments malformés renvoie maintenant une erreur structurée normale, sans jamais faire tomber la requête entière |

## Fonctionnalités ajoutées (style Claude Code)

- **Todo list live** : le plan génère une liste de tâches, streamée et mise à
  jour en temps réel (`pending` → `in_progress` → `done`/`failed`) via
  l'événement `todo_update`.
- **`edit_file`** : remplacement ciblé d'une chaîne unique dans un fichier
  existant (comme un `str_replace`), plus sûr et plus lisible qu'une
  réécriture complète pour de petites corrections — utilisé en priorité
  par la boucle de fix.
- **`list_dir`** : permet à l'agent d'explorer l'arborescence du workspace
  au lieu de deviner les noms de fichiers.
- **Multi-modèle Ollama** : `model` optionnel dans le body de `/ask`,
  validé contre une whitelist (`AGENT_ALLOWED_MODELS`) — un client ne peut
  pas faire exécuter n'importe quel modèle arbitraire.
- **Architecture multi-provider prête, mais Ollama-only par défaut** :
  `llm/base.py` définit le contrat (`chat`, `chat_stream`,
  `supports_model`) pour qu'un provider externe puisse être ajouté plus
  tard (une nouvelle classe dans `llm/`, zéro changement dans `core/`) —
  mais aucun n'est implémenté à ce jour, et `llm/registry.py` refuse
  explicitement tout provider ≠ "ollama" tant que
  `AGENT_ALLOW_EXTERNAL_PROVIDERS=true` n'est pas posé manuellement. Par
  défaut, tout reste local : aucun appel réseau hors de la machine où
  tourne Ollama.
- **Erreurs explicites** : toute panne LLM (Ollama éteint, timeout, modèle
  refusé) remonte un message clair au lieu d'un plan vide silencieux.
- **Streaming token par token** : `thinking_delta`/`content_delta` en
  temps réel pendant la génération (réflexion ET réponse), au lieu
  d'attendre la fin du tour pour tout recevoir d'un bloc.
- **Undo / Rollback** : chaque écriture de fichier est checkpointée ;
  `/checkpoints/{run_id}` et `/undo/{run_id}` permettent d'inspecter et
  d'annuler les modifications, étape par étape.
- **Arrêt vraiment immédiat** : `/stop` interrompt le streaming en cours
  ET tue un process shell en cours d'exécution (groupe de process entier
  via `os.killpg`, pas juste le shell parent).
- **Lecture de PDF** : `inspect_pdf` / `read_pdf` pour que l'agent puisse
  lire des documents PDF du workspace (specs, rapports...).
- **Recherche web** : `web_search` / `web_fetch` via DuckDuckGo HTML +
  BeautifulSoup, sans API tierce ni clé à configurer. Le LLM juge la
  pertinence des résultats via leurs extraits et relance une recherche
  reformulée si besoin, dans le même run.
- **Routage automatique de modèle** : le planner classe la tâche
  (code/redaction/synthese/reflexion) et l'exécution utilise
  automatiquement le modèle Ollama configuré pour cette catégorie.
- **Protection des commandes longues** : `pip install` n'est jamais tué
  par un timeout interne ni par un `/stop` accidentel — confirmation
  explicite (`force: true`) requise pour l'interrompre.

## Points d'attention pour la suite

- Le mode JSON d'Ollama (`format: "json"`) nécessite une version
  d'Ollama relativement récente — vérifie `ollama --version` si le
  planner échoue systématiquement au parsing.
- `web_search`/`web_fetch` (`tools/web_tools.py`) font du scraping HTML
  direct, pas un appel d'API stable : si DuckDuckGo change la structure
  de sa page HTML (classes CSS `.result`, `.result__title`,
  `.result__snippet`), le parsing peut casser silencieusement (retourner
  `count: 0` alors que des résultats existent). Si ça arrive, c'est ce
  fichier qu'il faut ajuster — pas un problème réseau.
- `AGENT_ALLOWED_MODELS` doit être tenu à jour avec les modèles réellement
  installés (`ollama list`) — mais les modèles du mapping par catégorie
  (`AGENT_MODEL_CODE`, etc.) y sont ajoutés automatiquement, donc pas
  besoin de les dupliquer manuellement dans `AGENT_ALLOWED_MODELS`.
- La classification `task_category` dépend de la qualité du modèle de
  planning : un petit modèle peut mal classer des demandes ambiguës ou
  mixtes (ex: "résume ce code et corrige le bug"). En cas de doute, le
  fallback est toujours `"code"` plutôt qu'une catégorie aléatoire.
- La mémoire (`core/memory.py`) est en RAM, par processus : elle est
  perdue au redémarrage du serveur. Si la persistance entre redémarrages
  devient nécessaire, c'est le seul endroit à swapper (même pattern que
  `storage/runs.py`, qui est déjà pensé pour ça).
- `start_new_session=True` + `os.killpg` (utilisés par `/stop` pour tuer
  un shell en cours) sont des primitives **Unix** (Linux/macOS). Sous
  Windows natif (hors WSL), `shell_tool.py` nécessiterait une adaptation
  (`CREATE_NEW_PROCESS_GROUP` + `CTRL_BREAK_EVENT` côté Windows).
- Les checkpoints (`core/checkpoints.py`) sont en RAM par run, avec un
  doublon JSONL sur disque pour survivre à un redémarrage tant que
  `LOG_DIR` n'est pas nettoyé manuellement — mais ils ne sont jamais
  purgés automatiquement (pas de TTL). À surveiller si beaucoup de runs
  s'accumulent sur un déploiement long-vivant.
- Aucun provider LLM externe (Anthropic, OpenAI...) n'est implémenté
  dans ce projet — uniquement Ollama. `AGENT_ALLOW_EXTERNAL_PROVIDERS`
  prépare le terrain architectural pour ne jamais en activer un par
  accident si un jour quelqu'un en code un, mais il n'y a rien derrière
  ce flag aujourd'hui : le mettre à `true` sans provider implémenté
  lève juste une erreur explicite, pas un appel réseau caché.
- La protection "commande longue" se base sur le préfixe de la commande
  (`tools/process_registry.py::PROTECTED_COMMAND_PREFIXES` : `pip`,
  `pip3`, `python `, `python3 `). Si d'autres commandes légitimement
  longues sont utilisées (ex: `npm install`, des compilations), ajoute
  leur préfixe à ce tuple.
