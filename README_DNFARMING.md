# Configuration du Bot DN Farming

Ce document explique comment configurer le fichier `config/dnfarming.json` pour le bot de delta-neutral farming.

## Structure du fichier

Le fichier `config/dnfarming.json` doit contenir les paramètres suivants :

```json
{
    "symbol": "BTC",
    "leverage": 10,
    "margin": 20,
    "min_duration": 1,
    "max_duration": 1,
    "num_cycles": 3,
    "delay_between_cycles": 0,
    "rebalance_threshold": 10.0
}
```

## Paramètres détaillés

### `symbol` (string, requis)
- **Description** : La paire de trading à utiliser
- **Exemples** : `"BTC"`, `"ETH"`, `"SOL"`
- **Format** : Le symbole sera automatiquement converti en majuscules
- **Note** : Le bot utilisera la paire `SYMBOL-USD` (ex: `BTC-USD`)

### `leverage` (integer, requis)
- **Description** : Le levier à appliquer pour les trades
- **Valeur minimale** : `1` (pas de levier)
- **Exemples** : `3`, `10`, `20`, `50`
- **Recommandation** : Utilisez un levier modéré (5-10x) pour réduire les risques

### `margin` (float, requis)
- **Description** : La marge (en USDC) à utiliser par trade sur chaque compte
- **Valeur minimale** : Doit être > 0
- **Exemples** : `20.0`, `50.0`, `100.0`
- **Note** : Cette marge sera utilisée sur chaque compte (long et short), donc le total par cycle sera `margin × 2`

### `min_duration` (integer, requis)
- **Description** : Durée minimale (en minutes) pendant laquelle les trades resteront ouverts
- **Valeur minimale** : Doit être > 0
- **Exemples** : `1`, `30`, `60`
- **Note** : La durée réelle sera aléatoirement choisie entre `min_duration` et `max_duration`

### `max_duration` (integer, requis)
- **Description** : Durée maximale (en minutes) pendant laquelle les trades resteront ouverts
- **Valeur minimale** : Doit être >= `min_duration`
- **Exemples** : `2`, `60`, `120`
- **Note** : Si `min_duration` = `max_duration`, tous les cycles auront la même durée

### `num_cycles` (integer, requis)
- **Description** : Nombre de cycles de trading à exécuter
- **Valeur minimale** : Doit être >= 1
- **Exemples** : `3`, `5`, `10`
- **Note** : Un cycle = ouverture des positions → attente → fermeture → rebalancing (si nécessaire)

### `delay_between_cycles` (integer, requis)
- **Description** : Délai en minutes entre chaque cycle
- **Valeur minimale** : Doit être >= 0
- **Exemples** : `0` (pas de délai), `5`, `10`, `30`
- **Note** : 
  - `0` = pas de délai, le prochain cycle démarre immédiatement après le rebalancing
  - Un compte à rebours sera affiché pendant le délai

### `rebalance_threshold` (float, requis)
- **Description** : Seuil de différence (en USDC) entre les deux comptes pour déclencher un rebalancing automatique
- **Valeur minimale** : Doit être >= 0
- **Exemples** : `10.0`, `15.0`, `20.0`
- **Fonctionnement** :
  - Si la différence entre les deux comptes > `rebalance_threshold`, un rebalancing automatique sera effectué
  - Le rebalancing se fait au démarrage du bot et entre chaque cycle
  - Si la différence est <= `rebalance_threshold`, aucun rebalancing ne sera effectué
- **Recommandation** : Utilisez un seuil de 10-20 USDC pour éviter les rebalancings trop fréquents

## Exemple de configuration complète

```json
{
    "symbol": "BTC",
    "leverage": 10,
    "margin": 50.0,
    "min_duration": 30,
    "max_duration": 60,
    "num_cycles": 5,
    "delay_between_cycles": 5,
    "rebalance_threshold": 15.0
}
```

**Explication de cet exemple** :
- Trade la paire **BTC-USD** avec un **levier 10x**
- Utilise **50 USDC de marge** par trade (100 USDC total par cycle)
- Les trades resteront ouverts entre **30 et 60 minutes** (durée aléatoire)
- Exécutera **5 cycles** au total
- Attendra **5 minutes** entre chaque cycle
- Rebalancera automatiquement si la différence entre les comptes dépasse **15 USDC**

## Notes importantes

1. **Balances suffisantes** : Assurez-vous que chaque compte Extended a suffisamment de fonds pour couvrir la marge configurée
2. **Alternance des positions** : Le bot alterne automatiquement les positions (cycle 1: compte1 LONG/compte2 SHORT, cycle 2: compte1 SHORT/compte2 LONG, etc.)
3. **Rebalancing automatique** : Le bot vérifie et rebalance automatiquement si nécessaire, mais seulement si la différence dépasse le seuil configuré
4. **Fichier .env requis** : Les credentials des comptes (clés API, adresses, etc.) doivent être configurés dans un fichier `.env` à la racine du projet

## Validation

Le bot valide automatiquement tous les paramètres au démarrage. Si un paramètre est invalide ou manquant, une erreur descriptive sera affichée.

## Support

En cas de problème, vérifiez :
- Que tous les paramètres sont présents et valides
- Que les valeurs respectent les contraintes (min/max)
- Que les balances des comptes sont suffisantes pour la marge configurée

