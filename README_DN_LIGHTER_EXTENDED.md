# 📊 DN Lighter Extended - Bot de Trading Delta Neutre

Bot de trading delta neutre automatisé entre **Extended Exchange** et **Lighter Exchange** avec support des ordres LIMIT et MARKET.

## 🎯 Fonctionnalités

- ✅ **Trading Delta Neutre** : Positions opposées (LONG/SHORT) sur Extended et Lighter
- ✅ **Mode LIMIT** : Ordres maker sur Extended (0% frais) avec suivi dynamique du prix
- ✅ **Mode MARKET** : Ordres market simultanés sur les deux exchanges
- ✅ **Rebalancing Automatique** : Transfert automatique de fonds entre les comptes
- ✅ **Monitoring PnL** : Affichage en temps réel du PnL non réalisé
- ✅ **Gestion des Erreurs** : Retry automatique et gestion robuste des échecs

## 📋 Prérequis

- Python 3.10 ou supérieur
- Comptes actifs sur Extended Exchange et Lighter Exchange
- Fonds USDC sur les deux comptes (minimum : 2x la marge configurée)
- Clés API pour Extended et Lighter
- Wallet Arbitrum avec clé privée (pour le rebalancing)

## 🔧 Installation

### 1. Installer les dépendances Python

```bash
pip install -r requirements.txt
```

**Dépendances principales :**
- `python-dotenv` : Gestion des variables d'environnement
- `loguru` : Système de logging
- `web3` : Interactions avec Arbitrum (rebalancing)
- `x10-python-trading-starknet` : SDK Extended Exchange
- `lighter-python` : SDK Lighter Exchange (installé depuis le dossier `lighter-python-main`)

### 2. Installer le SDK Lighter (si nécessaire)

Si le SDK Lighter n'est pas installé :

```bash
cd lighter-python-main
pip install -e .
cd ..
```

## ⚙️ Configuration

### 1. Fichier `.env`

Créez un fichier `.env` à la racine du projet avec les variables suivantes :

#### Configuration Extended Exchange

```env
# Extended Exchange - Compte 1
ACCOUNT1_NAME=Extended Account
ACCOUNT1_API_KEY=votre_api_key_extended
ACCOUNT1_PUBLIC_KEY=votre_stark_public_key
ACCOUNT1_PRIVATE_KEY=votre_stark_private_key
ACCOUNT1_VAULT_ID=104228
ACCOUNT1_ARBITRUM_ADDRESS=0x...
ACCOUNT1_ARBITRUM_PRIVATE_KEY=0x...
```

#### Configuration Lighter Exchange

```env
# Lighter Exchange
LIGHTER_NAME=Lighter Account
LIGHTER_ACCOUNT_INDEX=6336
LIGHTER_L1_ADDRESS=0x...
LIGHTER_ARBITRUM_ADDRESS=0x...
LIGHTER_ARBITRUM_PRIVATE_KEY=0x...
LIGHTER_L1_PRIVATE_KEY=0x...

# Clés API Lighter (au moins une requise)
LIGHTER_API_KEY_0=votre_api_key_lighter_0
# Ou utilisez une seule clé :
# LIGHTER_API_KEY=votre_api_key_lighter
```

**⚠️ Important :**
Pour le trouver, cliquez sur le bouton wallet en haut a droite de l'interface lighter, puis Explorer, ce sera le numéro affiché après le #


### 2. Fichier `config/dnfarming.json`

Configurez les paramètres de trading dans `config/dnfarming.json` :

```json
{
    "symbol": "BTC",
    "leverage": 30,
    "margin": 3000,
    "min_duration": 10,
    "max_duration": 13,
    "num_cycles": 20,
    "delay_between_cycles": 1,
    "rebalance_threshold": 700.0,
    "pnl_check_delay": 10,
    "minimal_pnl": 0,
    "order_mode": "limit",
    "limit_order_timeout": 20,
    "withdraw_to_extended": false
}
```

#### Paramètres détaillés

| Paramètre | Type | Description | Exemple |
|-----------|------|-------------|---------|
| `symbol` | string | Paire à trader | `"BTC"`, `"ETH"` |
| `leverage` | integer | Levier utilisé | `30` (30x) |
| `margin` | float | Marge en USDC par exchange | `3000` ($3000) |
| `min_duration` | integer | Durée minimale du cycle (minutes) | `10` |
| `max_duration` | integer | Durée maximale du cycle (minutes) | `13` |
| `num_cycles` | integer | Nombre de cycles à exécuter | `20` |
| `delay_between_cycles` | integer | Délai entre cycles (minutes) | `1` |
| `rebalance_threshold` | float | Seuil de rebalancing (USDC) | `700.0` |
| `pnl_check_delay` | integer | Délai d'attente si PnL négatif (minutes) | `10` |
| `minimal_pnl` | float | Seuil minimal de PnL pour fermeture | `0` |
| `order_mode` | string | Mode d'ordre : `"limit"` ou `"market"` | `"limit"` |
| `limit_order_timeout` | integer | Timeout pour ordres LIMIT (secondes) | `20` |

#### Explications des paramètres

- **`margin`** : Montant en USDC utilisé par exchange. Le bot utilisera 90% de cette valeur pour garantir la sécurité.
- **`rebalance_threshold`** : Si la différence entre les balances Extended et Lighter dépasse ce seuil, le bot rebalance automatiquement.
- **`pnl_check_delay`** : Si le PnL total est négatif à la fin du cycle, le bot attend ce délai avant de fermer (pour laisser le temps de récupérer).
- **`minimal_pnl`** : Si le PnL total atteint ou dépasse ce seuil, le bot ferme immédiatement les positions.
- **`order_mode`** :
  - `"limit"` : Ordre LIMIT sur Extended (maker, 0% frais), puis MARKET sur Lighter après fill
  - `"market"` : Ordres MARKET simultanés sur les deux exchanges

## 🚀 Utilisation

### Lancer le bot

```bash
python dn_lighter_extended.py
```

### Arrêter le bot

Appuyez sur `Ctrl+C`. Le bot fermera automatiquement toutes les positions ouvertes avant de s'arrêter.

## 🔄 Mode de Fonctionnement

### Mode LIMIT 

**Avantages :**
- ✅ 0% frais sur Extended (maker)
- ✅ Suivi dynamique du prix en temps réel
- ✅ Réajustement automatique si le marché bouge

**Fonctionnement :**
1. Compare les prix Extended vs Lighter
2. Place un ordre LIMIT sur Extended au bid/ask exact (maker)
3. Surveille le marché en temps réel via WebSocket
4. Réajuste l'ordre si le prix s'éloigne de plus de $0.10
5. Une fois l'ordre Extended fill → place un ordre MARKET sur Lighter
6. Attend la durée du cycle avec monitoring PnL
7. Ferme les positions avec vérification PnL

**Exemple de log :**
```
📝 PLACEMENT DES ORDRES (MODE LIMIT) POUR BTC
Extended > Lighter → SHORT Extended @ $91224.00 (LIMIT, ask exact) | LONG Lighter (MARKET)
✅ Ordre LIMIT Extended placé: abc123
⏳ Ordre @ $91224.00 | Marché @ $91225.00 | Écart: $1.00 (0.001%) | 5s
✅ Ordre Extended FILL détecté: 0.986600 BTC
✅ Ordre MARKET Lighter placé: xyz789
```

### Mode MARKET

**Fonctionnement :**
1. Compare les prix Extended vs Lighter
2. Place les ordres MARKET simultanément sur les deux exchanges
3. Attend la durée du cycle avec monitoring PnL
4. Ferme les positions avec vérification PnL

## 📊 Monitoring PnL

Le bot affiche le PnL en temps réel pendant l'attente du cycle :

```
📊 PnL BTC | Extended: LONG 0.986600 = $+12.34 | Lighter: SHORT 0.986600 = $-8.90 | Total: $+3.44 | ⏱️ 05:23 / 04:37
```

- **Extended PnL** : Calculé avec mid_price (bid+ask)/2 depuis l'orderbook WebSocket
- **Lighter PnL** : Calculé avec mark_price depuis l'API Explorer
- **Total PnL** : Somme des deux PnL

## 🔄 Rebalancing Automatique

Le bot vérifie les balances entre chaque cycle :

- Si la différence > `rebalance_threshold` → Transfert automatique
- Transfert via Arbitrum (Extended ↔ Lighter)
- Utilise les bridges Rhino.fi (Extended) et Lighter fast withdraw

**Exemple :**
```
💰 VÉRIFICATION DES BALANCES ENTRE CYCLES
Extended: $4563.14
Lighter: $3558.96
Différence: $1004.18 > seuil $700.00
🔄 REBALANCING EXTENDED <-> LIGHTER
📤 Transfert: Extended → Lighter
```

## ⚠️ Gestion des Erreurs

- **Ordre rejeté** : Le bot réessaie automatiquement (max 5 tentatives en mode LIMIT)
- **Rebalancing échoué** : Le bot continue avec les balances actuelles (warning)
- **Position partielle** : Le bot ferme automatiquement les positions partielles
- **Ctrl+C** : Le bot ferme toutes les positions avant de s'arrêter

## 📝 Logs

Les logs sont sauvegardés dans :
- **Console** : Affichage en temps réel (niveau INFO)
- **Fichier** : `dn_lighter_extended.log` (niveau DEBUG, rotation 10 MB, rétention 7 jours)

## 🔍 Vérification des Positions

Le bot utilise :
- **Extended** : WebSocket account pour les positions
- **Lighter** : API Explorer (plus fiable après placement d'ordre)

## 💡 Conseils d'Utilisation

1. **Démarrage** : Commencez avec `num_cycles: 1` pour tester
2. **Margin** : Utilisez au moins 2x la marge configurée sur chaque compte
3. **Mode LIMIT** : Recommandé pour réduire les frais (0% sur Extended)
4. **Monitoring** : Surveillez les logs pour détecter les problèmes
5. **Rebalancing** : Le seuil de 700 USDC est un bon compromis

## 🐛 Dépannage

### Erreur "no running event loop"
- Vérifiez que le SDK Lighter est correctement installé
- Redémarrez le bot

### Balance Lighter non détectée
- Vérifiez `LIGHTER_L1_ADDRESS` dans le `.env`
- Vérifiez `LIGHTER_ACCOUNT_INDEX` (trouvez-le sur lighter.xyz)

### Ordre LIMIT rejeté
- Le bot réessaie automatiquement
- Si tous les retries échouent, le bot s'arrête (en mode LIMIT)

### Rebalancing échoué
- Vérifiez les clés privées Arbitrum dans le `.env`
- Vérifiez que vous avez des fonds sur Arbitrum
- Le bot continue même si le rebalancing échoue

## 📚 Structure du Projet

```
deltafund/
├── dn_lighter_extended.py      # Bot principal
├── config/
│   └── dnfarming.json          # Configuration
├── exchanges/
│   ├── extended_api.py         # API Extended
│   ├── lighter_api.py          # API Lighter
│   └── rebalancing.py          # Gestionnaire de rebalancing
├── .env                        # Variables d'environnement (à créer)
└── README_DN_LIGHTER_EXTENDED.md  # Ce fichier
```

## 🔐 Sécurité

- ⚠️ **Ne commitez JAMAIS** le fichier `.env`
- ⚠️ **Protégez vos clés privées** : Ne les partagez jamais
- ⚠️ **Testez d'abord** avec de petites marges
- ⚠️ **Surveillez** les logs pour détecter les anomalies

## 📞 Support

En cas de problème :
1. Vérifiez les logs dans `dn_lighter_extended.log`
2. Vérifiez que toutes les variables `.env` sont correctes
3. Vérifiez que les balances sont suffisantes sur les deux exchanges

---

**Version** : 1.0  
**Dernière mise à jour** : 2025-01-05




