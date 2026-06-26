<div align="center">

# 🚀 SynDemos

### Une plateforme IA locale réunissant un assistant conversationnel, un système RAG et un agent autonome piloté par des LLM.

*Construite autour d'Ollama, FastAPI et de modèles GGUF exécutés entièrement en local.*

---

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688.svg)
![Ollama](https://img.shields.io/badge/Ollama-Local_LLM-black.svg)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

</div>

---

# 📖 Présentation

**SynDemos** est une plateforme expérimentale dédiée aux **LLM locaux**.

Le projet est né d'un constat simple :

> Les modèles de langage sont aujourd'hui capables de bien plus que répondre à des questions. Ils peuvent rechercher de l'information, manipuler des fichiers, utiliser des outils, écrire du code, interagir avec un utilisateur et automatiser des tâches complexes.

Plutôt que de proposer un simple chatbot, SynDemos rassemble plusieurs briques complémentaires dans une architecture unique :

- 💬 un assistant conversationnel moderne
- 📚 un moteur RAG (Retrieval Augmented Generation)
- 🤖 un agent autonome capable d'utiliser des outils
- 🧠 plusieurs modèles spécialisés exécutés via Ollama
- 🌐 une interface Web unique
- 🐳 un déploiement simplifié avec Docker

L'ensemble du projet est pensé pour fonctionner **entièrement en local**, sans dépendre d'API commerciales ni envoyer de données vers des services externes.

---

# ✨ Pourquoi SynDemos ?

Aujourd'hui, la majorité des applications IA se limitent à une simple interface de chat.

SynDemos va plus loin.

Le projet cherche à démontrer qu'un LLM local peut devenir un véritable environnement de travail capable de :

- discuter avec un utilisateur
- rechercher des informations dans des documents
- utiliser plusieurs modèles spécialisés
- effectuer des recherches Web
- générer du code
- modifier des fichiers
- lancer des commandes système
- planifier des tâches complexes
- vérifier automatiquement son propre travail

L'objectif est de proposer une base technique claire, modulaire et facilement extensible pour expérimenter autour des modèles de langage modernes.

---

# 🌟 Fonctionnalités

## 💬 Assistant conversationnel

Le chat constitue le point d'entrée principal de l'application.

Fonctionnalités :

- conversations persistantes
- réponses en streaming
- historique des échanges
- sélection dynamique du modèle
- intégration transparente du RAG
- interface légère
- fonctionnement 100 % local

---

## 📚 RAG

Le système de Retrieval Augmented Generation permet au modèle de répondre à partir de documents locaux.

Il prend en charge :

- indexation des documents
- calcul des embeddings
- recherche sémantique
- récupération automatique du contexte
- enrichissement des réponses

---

## 🤖 Agent autonome

L'agent constitue un composant indépendant du chat.

Il est capable de :

- construire un plan
- raisonner étape par étape
- utiliser différents outils
- créer et modifier des fichiers
- lancer des commandes shell
- lire des PDF
- effectuer des recherches Web
- vérifier automatiquement ses résultats
- corriger ses erreurs
- diffuser son raisonnement en streaming

> 📄 La documentation complète de l'agent est disponible dans **`agent/README.md`**.

---

## 🧠 Plusieurs modèles spécialisés

Plutôt que d'utiliser un unique modèle pour toutes les tâches, SynDemos permet de spécialiser les modèles selon leurs domaines de compétence.

Par exemple :

| Domaine | Modèle |
|----------|---------|
| Conversation | Qwen3 8B |
| Génération de code | Qwen2.5 Coder |
| Documentation | Mistral 7B |
| Raisonnement | Qwen2.5 Instruct |

Cette approche permet d'obtenir de meilleures performances selon la nature des demandes.

---

# 🏗️ Architecture générale

Le dépôt est organisé comme un **workspace complet** regroupant :

- les sources de SynDemos
- le workspace de l'agent
- les modèles GGUF
- les fichiers Docker

```text
AI_OS/
│
├── README.md
├── Dockerfile
├── docker-compose.yml
├── start.sh
│
├── SynDemos/
│   │
│   ├── agent/
│   ├── backend/
│   ├── data/
│   ├── ui/
│   └── run.py
│
├── workforce/
│   ├── .venv/
│   └── logs/
│
└── models/
    ├── Mistral_Q4/
    ├── Qwen_Code_Q4/
    ├── Qwen_Instruct_Q4/
    └── Qwen3_8b/
```

Le dépôt est volontairement découpé en trois espaces distincts :

| Dossier | Description |
|----------|-------------|
| **SynDemos** | Contient l'ensemble du code source de l'application. |
| **workforce** | Workspace utilisé par l'agent autonome (logs, environnement Python, fichiers manipulés). |
| **models** | Contient les modèles GGUF ainsi que leurs Modelfiles utilisés par Ollama. |

Cette séparation permet de conserver un dépôt Git léger tout en partageant facilement les modèles entre plusieurs projets.

---

# 🧩 Architecture logicielle

L'ensemble de l'application repose sur une architecture modulaire.

```text
                                    Utilisateur
                                         │
                                         │
                                         ▼
                          ┌──────────────────────────┐
                          │        Interface UI      │
                          │      HTML / CSS / JS     │
                          └─────────────┬────────────┘
                                        │
                                   HTTP / SSE
                                        │
                                        ▼
                         ┌────────────────────────────┐
                         │       Backend FastAPI      │
                         └──────┬───────────┬─────────┘
                                │           │
                                │           │
                                ▼           ▼
                       Chat Engine      Agent Client
                            │                │
                            │                │
                  ┌─────────▼───────┐        │
                  │       RAG        │        │
                  │ Embeddings/Search│        │
                  └─────────┬────────┘        │
                            │                 │
                            └────────┬────────┘
                                     │
                                     ▼
                             Ollama (LLM Local)
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                │
                    ▼                ▼                ▼
               Qwen3 8B       Qwen2.5 Coder     Mistral
                                     │
                                     ▼
                           Agent Autonome (API)
                                     │
                      ┌──────────────┼──────────────┐
                      │              │              │
                      ▼              ▼              ▼
                  Shell         Fichiers       Recherche Web
                    ──────────────── 
                           │
                           ▼
                       Workspace
                      (workforce/)
```

Chaque composant possède une responsabilité bien définie :

- **UI** : interaction avec l'utilisateur.
- **Backend** : orchestration générale.
- **Chat Engine** : gestion des conversations.
- **RAG** : enrichissement des réponses.
- **Agent Client** : communication avec l'agent autonome.
- **Ollama** : exécution locale des modèles.
- **Agent** : planification et utilisation des outils.

Cette architecture permet de faire évoluer indépendamment chaque partie du projet.

---

# 📁 Arborescence détaillée

Le code source de SynDemos est contenu dans le dossier **SynDemos**.

```text
SynDemos/
│
├── agent/
│
├── backend/
│   ├── agent_client.py
│   ├── api.py
│   ├── chat.py
│   ├── files.py
│   ├── models.py
│   ├── rag.py
│   └── storage.py
│
├── data/
│   ├── embeddings/
│   └── threads/
│
├── ui/
│   ├── images/
│   └── index.html
│
└── run.py
```

Les sections suivantes détaillent le rôle de chacun de ces composants ainsi que leur interaction au sein de la plateforme.

---

# 🎯 Philosophie du projet

SynDemos repose sur quelques principes simples :

- **Local First** : tous les traitements sont réalisés sur la machine de l'utilisateur.
- **Modulaire** : chaque composant possède une responsabilité unique.
- **Extensible** : de nouveaux modèles ou outils peuvent être ajoutés facilement.
- **Transparent** : aucune dépendance à un fournisseur d'API propriétaire n'est imposée.
- **Pédagogique** : le code est organisé afin de rester lisible et facilement compréhensible.

L'objectif n'est pas uniquement de construire un assistant conversationnel, mais de proposer une véritable plateforme de démonstration autour des LLM modernes.

# 🚀 Installation

SynDemos peut être utilisé de deux façons :

- **Installation locale** (développement)
- **Installation Docker** (recommandée)

L'ensemble du projet repose sur **Ollama** pour l'exécution des modèles de langage.

---

# 📋 Prérequis

Avant de lancer SynDemos, assurez-vous de disposer de :

| Logiciel | Version recommandée |
|-----------|--------------------|
| Python | 3.11+ |
| Docker | dernière version |
| Docker Compose | dernière version |
| Ollama | dernière version |

Le projet a principalement été développé sous **Linux / WSL2**, mais reste facilement adaptable à d'autres environnements.

---

# 📂 Organisation du workspace

Le projet s'appuie sur un workspace organisé comme suit :

```text
AI_OS/
│
├── README.md
├── Dockerfile
├── docker-compose.yml
├── start.sh
│
├── SynDemos/
│
├── workforce/
│
└── models/
```

Les trois dossiers principaux ont chacun un rôle spécifique.

## SynDemos

Contient tout le code source.

```text
SynDemos/
```

---

## workforce

Workspace utilisé par l'agent autonome.

```text
workforce/
├── .venv/
└── logs/
```

On y retrouve notamment :

- l'environnement Python
- les journaux d'exécution
- les fichiers manipulés par l'agent

Ce dossier est volontairement séparé du dépôt Git.

---

## models

Ce dossier contient tous les modèles GGUF utilisés par Ollama.

```text
models/
│
├── Mistral_Q4/
├── Qwen_Code_Q4/
├── Qwen_Instruct_Q4/
└── Qwen3_8b/
└── Embed_BGE_m3/
```

Chaque dossier contient :

- le modèle GGUF
- un Modelfile
- éventuellement plusieurs variantes du modèle

Cette organisation permet de partager facilement les modèles entre plusieurs projets utilisant Ollama.

---

# 🧠 Téléchargement des modèles

SynDemos utilise plusieurs modèles spécialisés.

Ils doivent être téléchargés au format **GGUF** avant la création des modèles Ollama.

---

## qwen3:8b : Qwen3 8B

Modèle principal utilisé par l'agent autonome.

**Version recommandée**

```
Q4_K_M
```

Téléchargement :

https://huggingface.co/Qwen/Qwen3-8B-GGUF/blob/main/Qwen3-8B-Q4_K_M.gguf

Chemin conseillé:
/models/Qwen3_8b/
---

## coder : Qwen2.5 Coder 7B

Utilisé pour les tâches de génération de code.

**Version recommandée**

```
Q4_K_M
```

Téléchargement :

https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/tree/main

Chemin conseillé:
/models/Qwen_Code_Q4
---

## reasoning : Qwen2.5 Instruct 7B

Utilisé pour les tâches de raisonnement général.

**Version recommandée**

```
Q4_K_M
```

Téléchargement :

https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/blob/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf

Chemin conseillé:
/models/Qwen_Instruct_Q4
---

## docs : Mistral 7B Instruct

Utilisé principalement pour les tâches de rédaction et de documentation.

**Version recommandée**

```
Q4_K_M
```

Téléchargement :

https://huggingface.co/bartowski/Mistral-7B-Instruct-v0.3-GGUF/blob/main/Mistral-7B-Instruct-v0.3-Q4_K_M.gguf

Chemin conseillé:
/models/Mistral_Q4
---

## embeded : BGE M3

Utilisé principalement pour le system de RAG

**Version recommandée**

```
Q4_K_M
```

Téléchargement :

https://huggingface.co/gpustack/bge-m3-GGUF/tree/main
---

# 📄 Les Modelfiles

Ollama ne charge pas directement un fichier GGUF.

Chaque modèle est déclaré à l'aide d'un **Modelfile**.

Exemple :

```dockerfile
FROM /mnt/d/dev/ai_os/models/Mistral

PARAMETER temperature 0.7

SYSTEM """
Tu réponds en français.
"""
```

Le Modelfile permet notamment de définir :

- le modèle GGUF utilisé
- le prompt système
- la température
- les paramètres Ollama

---

# 🐳 Docker

Le projet fournit directement les fichiers nécessaires au déploiement.

```text
Dockerfile
docker-compose.yml
start.sh
```

Aucune configuration supplémentaire n'est nécessaire une fois les modèles téléchargés.

---

# Dockerfile

Le Dockerfile prépare un environnement complet contenant :

- Python
- Ollama
- Git
- Curl
- les dépendances Python

Il expose les ports suivants :

| Port | Utilisation |
|------|-------------|
| 11434 | Ollama |
| 8000 | Agent autonome |
| 8080 | Interface Web |
| 9000 | Backend |

Le point d'entrée du conteneur est :

```bash
/start.sh
```

---

# docker-compose.yml

Le fichier Docker Compose orchestre l'ensemble de l'environnement.

Il :

- construit l'image Docker
- monte les projets
- monte les modèles
- conserve les modèles Ollama
- expose les différents services

Les volumes montés sont notamment :

```text
/workspace/SynDemos

/workspace/workforce

/models
```

Les modèles Ollama sont persistés grâce au volume :

```text
ollama_data
```

Ainsi, un redémarrage du conteneur ne nécessite pas de retélécharger les modèles.

---

# start.sh

Le script `start.sh` automatise complètement le démarrage du projet.

Au lancement du conteneur, il exécute successivement :

```text
1. Démarrage d'Ollama

↓

2. Vérification de sa disponibilité

↓

3. Création des modèles locaux

↓

4. Vérification des modèles installés

↓

5. Affichage des projets montés

↓

6. Lancement de SynDemos
```

Il crée automatiquement les modèles suivants :

| Nom Ollama | Utilisation |
|------------|-------------|
| qwen3:8b | conversation principale |
| coder | génération de code |
| docs | documentation |
| reasoning | raisonnement |

Cette étape évite d'avoir à créer manuellement les modèles après chaque installation.

---

# ▶️ run.py

Une fois le conteneur prêt, le script `run.py` démarre automatiquement les différents services.

```text
                 run.py
                    │
                    │
      ┌─────────────┼──────────────┐
      │             │              │
      ▼             ▼              ▼
 Backend API     Interface      Agent
 FastAPI          Web          Autonome
```

Les services sont ensuite disponibles sur :

| Service | Adresse |
|----------|----------|
| Backend | http://localhost:9000 |
| Interface | http://localhost:8080 |
| Agent | http://localhost:8000 |
| Ollama | http://localhost:11434 |

L'ensemble peut être arrêté proprement avec **CTRL+C**.

---

# ⚙️ Configuration

La majorité de la configuration de l'agent est centralisée dans :

```text
SynDemos/agent/config.py
```

Ce fichier constitue **l'unique source de vérité** pour tous les paramètres de l'agent.

On y retrouve notamment :

- le chemin du workspace
- l'environnement virtuel
- les modèles utilisés
- les timeouts
- les limites d'exécution
- la mémoire conversationnelle
- la politique de sécurité shell
- les modèles autorisés
- les paramètres Ollama

Toutes les valeurs sont configurables via des variables d'environnement.

Aucun chemin important n'est codé en dur ailleurs dans le projet.

> **⚠️ Si vous adaptez SynDemos à une autre organisation de dossiers, pensez à modifier en priorité `agent/config.py`. `start.sh`. et les fichiers de configuration Docker **

---

# ▶️ Lancement

Une fois les modèles téléchargés et les dossiers correctement organisés, il suffit d'exécuter :

```bash
docker compose up --build
```

Le script de démarrage se charge automatiquement :

- de lancer Ollama
- de créer les modèles
- de démarrer le backend
- de lancer l'interface Web
- de lancer l'agent autonome

Quelques instants plus tard, l'application est entièrement opérationnelle.

---

# 🏛️ Architecture interne de SynDemos

Contrairement à une application de chat classique, SynDemos est composé de plusieurs services indépendants qui collaborent afin de fournir une expérience unifiée.

Chaque composant possède une responsabilité bien définie, ce qui facilite la maintenance, les évolutions et les expérimentations autour des modèles de langage.

---

# 🧩 Vue d'ensemble

```text
                                     Utilisateur
                                           │
                                           │
                                           ▼
                           ┌─────────────────────────┐
                           │       Interface Web     │
                           │     HTML / CSS / JS     │
                           └────────────┬────────────┘
                                        │
                           HTTP / Streaming (SSE)
                                        │
                                        ▼
                     ┌───────────────────────────────────┐
                     │          Backend FastAPI          │
                     └──────────────┬────────────────────┘
                                    │
              ┌─────────────────────┼──────────────────────┐
              │                     │                      │
              ▼                     ▼                      ▼
         Chat Engine            Gestion RAG         Agent Client
              │                     │                      │
              │                     ▼                      │
              │              Embeddings                  HTTP
              │              Recherche                   │
              │              Documents                   ▼
              │                                    Agent Autonome
              │                                           │
              └──────────────────────┬────────────────────┘
                                     ▼
                              Ollama (LLM Local)
                                     │
                 ┌───────────────────┼────────────────────┐
                 ▼                   ▼                    ▼
            Qwen3 8B           Qwen Coder          Mistral 7B
```

Le backend agit comme le chef d'orchestre de toute la plateforme.

Il ne réalise pas lui-même les traitements IA ; il distribue les demandes vers les composants appropriés.

---

# 💬 Le Chat

Le module de chat constitue le cœur de l'application.

Il reçoit les messages provenant de l'interface Web et se charge de produire une réponse en utilisant le modèle sélectionné.

Son rôle est de :

- gérer les conversations
- maintenir le contexte
- utiliser le RAG lorsque nécessaire
- communiquer avec Ollama
- diffuser les réponses en streaming

Le backend reste volontairement indépendant de l'interface utilisateur.

Ainsi, n'importe quel client HTTP pourrait dialoguer avec SynDemos sans modifier le cœur de l'application.

---

# 🔄 Cycle d'une conversation

Lorsqu'un utilisateur envoie un message, plusieurs étapes sont exécutées.

```text
Utilisateur

    │

    ▼

Interface Web

    │

    ▼

Backend FastAPI

    │

    ▼

Récupération du thread

    │

    ▼

Recherche RAG (si nécessaire)

    │

    ▼

Construction du prompt

    │

    ▼

Ollama

    │

    ▼

Streaming des tokens

    │

    ▼

Historique sauvegardé

    │

    ▼

Interface Web
```

Ce fonctionnement permet d'intégrer facilement :

- plusieurs modèles
- plusieurs conversations
- plusieurs utilisateurs

sans modifier l'architecture générale.

---

# 🧠 Gestion des modèles

Le backend centralise entièrement la gestion des modèles.

Le fichier :

```text
backend/models.py
```

est responsable de :

- récupérer les modèles disponibles
- sélectionner le modèle actif
- vérifier leur disponibilité
- dialoguer avec Ollama

Cette séparation évite que plusieurs composants interrogent directement Ollama.

Le backend devient ainsi l'unique point d'accès aux modèles.

---

# 📚 Le système RAG

Le module RAG permet d'améliorer les réponses du modèle à partir d'une base documentaire.

Le principe est le suivant :

```text
Question utilisateur

        │

        ▼

Calcul de l'embedding

        │

        ▼

Recherche vectorielle

        │

        ▼

Passages pertinents

        │

        ▼

Construction du contexte

        │

        ▼

Prompt enrichi

        │

        ▼

LLM
```

Le modèle ne répond donc plus uniquement à partir de ses connaissances générales.

Il peut également utiliser des documents indexés localement.

---

# 📂 Les données

Le dossier :

```text
data/
```

contient les informations persistantes du projet.

```text
data/

├── embeddings/

└── threads/
```

## embeddings/

Stocke les représentations vectorielles utilisées par le moteur RAG.

Ces embeddings permettent de retrouver rapidement les passages les plus pertinents.

---

## threads/

Contient l'historique des conversations.

Chaque conversation est conservée indépendamment afin de préserver son contexte.

Cette séparation facilite également l'ajout futur :

- d'utilisateurs multiples
- d'espaces de travail
- de projets indépendants

---

# 📡 Streaming

Le backend transmet les réponses du modèle en temps réel.

Au lieu d'attendre que toute la génération soit terminée, chaque morceau de texte est envoyé dès sa production.

```text
LLM

 │

 ▼

Token

 │

 ▼

Backend

 │

 ▼

SSE

 │

 ▼

Navigateur
```

Cette approche offre plusieurs avantages :

- meilleure réactivité
- sensation de fluidité
- réduction du temps d'attente perçu

Le principe est identique à celui utilisé par ChatGPT ou Claude.

---

# 🖥️ Interface utilisateur

Le dossier :

```text
ui/
```

contient une interface volontairement légère.

```text
ui/

├── index.html

└── images/
```

L'interface ne contient aucune logique métier.

Elle se contente :

- d'afficher les conversations
- d'envoyer les requêtes
- d'afficher le streaming
- de gérer l'expérience utilisateur

Toute la logique applicative reste concentrée dans le backend.

---

# 🔌 Communication avec l'agent autonome

Le backend peut déléguer certaines tâches à l'agent autonome.

Cette communication passe exclusivement par :

```text
backend/agent_client.py
```

Le backend conserve ainsi une séparation claire entre :

- les conversations classiques
- les tâches nécessitant un agent autonome

L'agent fonctionne comme un service indépendant possédant sa propre API.

Cette architecture permet de remplacer ou faire évoluer l'agent sans modifier le fonctionnement du chat.

---

# 🔄 Flux global d'une requête

```text
                         Utilisateur
                               │
                               ▼
                       Interface Web
                               │
                               ▼
                       Backend FastAPI
                               │
                ┌──────────────┼──────────────┐
                ▼              ▼              ▼
            Chat          RAG Engine     Agent Client
                │              │              │
                └───────┬──────┴──────────────┘
                        ▼
                    Ollama API
                        │
          ┌─────────────┼──────────────┐
          ▼             ▼              ▼
      Qwen3        Qwen Coder      Mistral
                        │
                        ▼
                Réponse en streaming
                        │
                        ▼
                 Interface utilisateur
```

Cette architecture présente plusieurs avantages :

- découplage des composants
- évolutivité
- simplicité des tests
- possibilité de remplacer un composant indépendamment des autres
- intégration facilitée de nouveaux modèles ou services

---

# 🤖 L'agent autonome

L'agent est un projet à part entière.

Il possède :

- sa propre API FastAPI
- son propre moteur
- ses outils
- sa mémoire
- son système de planification
- son moteur de vérification
- son système de streaming
- son architecture interne

Afin d'éviter de dupliquer la documentation, l'ensemble de son fonctionnement est décrit dans :

```text
SynDemos/
└── agent/
    └── README.md
```

Ce document couvre notamment :

- l'architecture interne
- le moteur d'exécution
- les outils disponibles
- les checkpoints
- le système Undo
- la recherche Web
- la lecture PDF
- le streaming SSE
- la machine à états
- la configuration avancée
- les fonctionnalités spécifiques à l'agent


---
# 🛣️ Roadmap

SynDemos est un projet en constante évolution.

Les fonctionnalités ci-dessous représentent les principales pistes d'amélioration prévues.

## Plateforme

- [x] Chat conversationnel
- [x] Backend FastAPI
- [x] Exécution locale via Ollama
- [x] Support Docker
- [x] Gestion de plusieurs modèles
- [x] Streaming des réponses
- [x] Historique des conversations
- [x] Intégration d'un agent autonome

---

## RAG

- [x] Recherche documentaire
- [x] Embeddings locaux
- [x] Base documentaire persistante
- [ ] Support de nouveaux formats (Word, Excel...)
- [x] Réindexation automatique
- [x] Recherche hybride (BM25 + embeddings)

---

## Agent

- [x] Planification automatique
- [x] Utilisation d'outils
- [x] Vérification automatique
- [x] Auto-correction
- [x] Recherche Web
- [x] Manipulation de fichiers
- [x] Streaming SSE

Voir la documentation dédiée :

```text
SynDemos/agent/README.md
```

---

## Interface

- [x] Chat moderne
- [x] Streaming
- [ ] Gestion des utilisateurs
- [ ] Paramètres avancés
- [x] Thèmes clair / sombre
- [ ] Visualisation des embeddings
- [x] Gestionnaire de documents
- [x] Historique des modèles

---

# 📸 Captures d'écran

Vous pouvez ajouter ici des captures de l'interface.

```text
docs/images/chat.png

docs/images/rag.png

docs/images/agent.png

docs/images/settings.png
```

Exemple :

```markdown
![Chat](docs/images/chat.png)

![Agent](docs/images/agent.png)
```

---

# 🚀 Ajouter un nouveau modèle

L'ajout d'un modèle Ollama est volontairement simple.

## 1. Télécharger le modèle GGUF

Déposez le modèle dans :

```text
models/
```

---

## 2. Créer son Modelfile

Exemple :

```dockerfile
FROM /models/MonModele.gguf

PARAMETER temperature 0.7

SYSTEM """
Tu réponds en français.
"""
```

---

## 3. Modifier `start.sh`

Ajouter simplement :

```bash
ollama create mon_modele -f /models/MonModele/Modelfile
```

---

## 4. Déclarer le modèle

Selon son utilisation :

- dans le backend
- dans `agent/config.py`
- dans l'interface utilisateur

Le modèle sera alors directement disponible dans SynDemos.

---

# ⚙️ Développement

L'architecture du projet a été pensée afin de faciliter l'ajout de nouveaux composants.

Chaque module possède une responsabilité clairement définie.

```text
Interface

↓

Backend

↓

Services spécialisés

↓

Ollama

↓

LLM
```

Cette séparation permet de modifier un composant sans impacter les autres.

---

# 🤝 Contribution

Les contributions sont les bienvenues.

Avant de proposer une Pull Request :

- créer une branche dédiée
- conserver le style de code existant
- documenter les nouvelles fonctionnalités
- tester les modifications

Exemple :

```bash
git checkout -b feature/ma-fonctionnalite
```

Puis :

```bash
git commit -m "Ajout de ..."
```

Enfin :

```bash
git push origin feature/ma-fonctionnalite
```

---

# 💡 Bonnes pratiques

Quelques recommandations pour tirer le meilleur parti de SynDemos :

- privilégier des modèles spécialisés selon les tâches
- conserver les modèles GGUF en dehors du dépôt Git
- laisser Ollama gérer les modèles créés
- utiliser Docker pour les démonstrations
- garder `agent/config.py` comme point central de configuration

---

# ❓ FAQ

## Pourquoi utiliser Ollama ?

Ollama permet d'exécuter des modèles de langage localement tout en offrant une API simple et unifiée.

---

## Les données quittent-elles ma machine ?

Non.

Par défaut, SynDemos fonctionne entièrement en local.

Les modèles sont exécutés par Ollama et aucune API distante n'est utilisée.

---

## Puis-je utiliser mes propres modèles ?

Oui.

Tout modèle compatible Ollama peut être ajouté via un Modelfile ou un pull (Bien modifier SynDemos/Agent/config.py pour l'agent et 

backend/models.py: 
MODEL_ENDPOINTS = {
    "coder": os.getenv("CODER_URL"),
    "docs": os.getenv("DOCS_URL"),
    "reasoning": os.getenv("REASONING_URL"),
}).

---

## Puis-je remplacer le frontend ?

Oui.

L'interface Web communique uniquement avec le backend FastAPI.

Tout client HTTP compatible peut donc être utilisé.

---

## Puis-je remplacer l'agent autonome ?

Oui.

L'agent est un service indépendant.

Le backend communique avec lui via son API.

---

# 📚 Documentation

Le projet est volontairement découpé en plusieurs documentations.

| Documentation | Description |
|---------------|-------------|
| **README.md** | Vue d'ensemble de SynDemos |
| **agent/README.md** | Documentation complète de l'agent autonome |

Le présent document décrit uniquement l'architecture générale de la plateforme.

La documentation de l'agent couvre en détail :

- le moteur d'exécution
- les outils
- la FSM
- les checkpoints
- le streaming
- les mécanismes de vérification
- les stratégies de correction
- la configuration avancée

---

# 🙏 Remerciements

SynDemos s'appuie sur plusieurs projets open source remarquables.

Merci notamment à leurs auteurs et communautés.

- Ollama
- FastAPI
- Hugging Face
- Qwen
- Mistral AI

---

# 📄 Licence

Ce projet est distribué sous licence **MIT**.

Vous êtes libre de :

- utiliser
- modifier
- distribuer
- adapter

le projet conformément aux conditions de cette licence.

---

# ❤️ À propos

SynDemos est avant tout un projet d'expérimentation autour des modèles de langage modernes.

L'objectif est de proposer une plateforme simple à comprendre, facilement extensible et entièrement locale, permettant aussi bien de discuter avec un assistant conversationnel que d'expérimenter des comportements d'agents autonomes capables d'utiliser des outils.

Le projet continuera d'évoluer au rythme des avancées des modèles open source et des nouvelles fonctionnalités de l'écosystème Ollama.

---

<div align="center">

## ⭐ Si ce projet vous plaît, n'hésitez pas à lui attribuer une étoile sur GitHub !

**Bon développement avec SynDemos ! 🚀**

</div>
