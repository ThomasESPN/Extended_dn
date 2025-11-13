# 🔐 Configuration des Wallets pour le Bot

Le bot utilise maintenant des **wallets blockchain** au lieu d'API keys traditionnelles.

---

## 📋 Prérequis

Vous devez avoir des wallets sur :
- **Extended** (ou Hyperliquid comme alternative 1h)
- **Variational** (ou un exchange 8h)

---

## 🔑 Configuration Rapide

**Bonne nouvelle** : Si tu utilises le **même wallet** pour Extended, Hyperliquid ET Variational, tu n'as besoin que d'une seule configuration !

### Configuration Simplifiée (1 wallet pour tout)

Édite `config/config.json` :

```json
{
  "wallet": {
    "address": "0xYOUR_WALLET_ADDRESS",
    "private_key": "YOUR_PRIVATE_KEY"
  },
  "exchanges": {
    "extended": {
      "api_url": "https://api.extended.finance",
      ...
    },
    "hyperliquid": {
      "api_url": "https://api.hyperliquid.xyz",
      ...
    },
    "variational": {
      "api_url": "https://api.variational.io",
      ...
    }
  }
}
```

**C'est tout !** Le bot utilisera automatiquement ce wallet pour tous les exchanges.

---

### Pour **Extended**

1. Aller sur https://app.extended.finance
2. Connecter votre wallet MetaMask
3. Aller dans Settings → API
4. Créer une **API Wallet** (recommandé)
5. Noter :
   - **Wallet Address** : `0x...` (adresse publique)
   - **Private Key** : Votre clé privée

### Pour **Hyperliquid**

1. Aller sur https://app.hyperliquid.xyz/API
2. Connecter votre wallet
3. Générer une **API Wallet** (optionnel mais recommandé)
4. Noter :
   - **Account Address** : `0x...`
   - **Private Key** : Votre clé privée

### Pour **Variational**

1. Aller sur https://omni.variational.io/
2. Connecter votre wallet
3. Utiliser les mêmes identifiants que votre wallet principal
4. Noter :
   - **Wallet Address** : `0x...`
   - **Private Key** : Votre clé privée

---

## ⚙️ Étape 2 : Configurer `config/config.json`

Ouvrez `config/config.json` et remplacez :

```json
{
  "exchanges": {
    "extended": {
      "name": "Extended",
      "wallet_address": "0xVOTRE_ADRESSE_EXTENDED",
      "private_key": "VOTRE_CLE_PRIVEE_EXTENDED",
      "api_url": "https://api.extended.finance",
      "funding_interval": 3600
    },
    "hyperliquid": {
      "name": "Hyperliquid",
      "wallet_address": "0xVOTRE_ADRESSE_HYPERLIQUID",
      "private_key": "VOTRE_CLE_PRIVEE_HYPERLIQUID",
      "api_url": "https://api.hyperliquid.xyz",
      "funding_interval": 3600
    },
    "variational": {
      "name": "Variational",
      "wallet_address": "0xVOTRE_ADRESSE_VARIATIONAL",
      "private_key": "VOTRE_CLE_PRIVEE_VARIATIONAL",
      "api_url": "https://api.variational.io",
      "funding_intervals": {
        "default": 28800
      }
    }
  }
}
```

---

## 🚨 SÉCURITÉ IMPORTANTE

### ⚠️ NE JAMAIS partager vos clés privées !

- ❌ Ne les commitez JAMAIS dans git
- ❌ Ne les envoyez JAMAIS par message
- ❌ Ne les stockez JAMAIS en clair sauf dans `config.json` (qui est dans `.gitignore`)

### 💡 Recommandations :

1. **Utilisez des API Wallets** au lieu de votre wallet principal
2. **Limitez les permissions** (trading only, pas de withdrawal)
3. **Testez d'abord sur TESTNET** avant mainnet
4. **Commencez avec de petits montants** ($100-500)

---

## 🧪 Étape 3 : Tester la connexion

```powershell
# Tester Hyperliquid
py src\exchanges\hyperliquid_api.py

# Devrait afficher :
# ✅ Balance: $XXX.XX USDC
# ✅ Open positions: 0
```

---

## 📊 Comment ça marche ?

### Delta-Neutral Trading

Le bot va :

1. **Scanner** les opportunités (via Loris Tools)
2. **Choisir** la meilleure (ex: ARK)
3. **Ouvrir 2 positions simultanément** :
   - 🟢 **LONG ARK** sur Hyperliquid (funding 1h)
   - 🔴 **SHORT ARK** sur Variational (funding 8h)

### Exemple avec ARK :

```
Position: $10,000 de chaque côté

LONG Hyperliquid:
- Funding: -0.00687 (on REÇOIT)
- Paiement: +$68.70 toutes les heures

SHORT Variational:
- Funding: -0.00782 (on REÇOIT aussi)
- Paiement: +$78.20 toutes les 8h

Résultat:
- Delta = 0 (prix monte/descend = aucun impact)
- Profit = fundings reçus des 2 côtés !
```

---

## 🛠️ Dépendances requises

Pour les wallets, installer :

```powershell
py -m pip install eth-account web3
```

---

## 🚀 Lancer le bot

Une fois configuré :

```powershell
# Mode AUTO (recommandé)
py src\main.py
```

Le bot va automatiquement :
- ✅ Scanner les 1429 symboles
- ✅ Trouver les 5 meilleures opportunités
- ✅ Ouvrir les positions delta-neutral
- ✅ Recevoir les fundings
- ✅ Fermer avant les paiements négatifs

---

## 📞 Support

Si tu as des questions :
- Check la doc Extended: https://docs.extended.finance
- Check la doc Hyperliquid: https://hyperliquid.gitbook.io
- Check la doc Variational: https://docs.variational.io

---

**⚠️ Disclaimer :** Trading = risque. Ne trade que ce que tu peux te permettre de perdre.
