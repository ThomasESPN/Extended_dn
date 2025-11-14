# ⚙️ Configuration du Bot - Guide Simple

## 📁 Fichiers de Configuration

### Dans le dossier `config/`

| Fichier | Utilité | Commiter sur Git ? |
|---------|---------|-------------------|
| `config.simple.json` | ✨ **Template ultra-simple** (recommandé) | ✅ Oui |
| `config.example.json` | Template complet (ancien système) | ✅ Oui |
| `config.json` | **TA config réelle** avec tes clés | ❌ **JAMAIS** |

---

## 🚀 Configuration Rapide (Recommandée)

### Étape 1: Copier le template simple

```powershell
cd config
cp config.simple.json config.json
```

### Étape 2: Éditer avec tes clés

```powershell
notepad config.json
```

### Étape 3: Remplir SEULEMENT ces 2 lignes

```json
{
  "wallet": {
    "address": "0xTON_WALLET_ADDRESS",
    "private_key": "TA_PRIVATE_KEY"
  },
  "auto_trading": {
    "enabled": true,  // ⚠️ false pour DRY-RUN, true pour LIVE
    "position_size_usd": 100
  }
}
```

**C'est tout ! Le reste utilise les valeurs par défaut.**

---

## 📝 Explication des Paramètres

### 🔐 Wallet (OBLIGATOIRE)

```json
{
  "wallet": {
    "address": "0x1234...abcd",     // Ton adresse publique
    "private_key": "0xabcd...5678"   // Ta clé privée (JAMAIS partager)
  }
}
```

**Où trouver tes clés ?**
- MetaMask: Menu → Détails du compte → Exporter la clé privée
- Autres wallets: Paramètres → Sécurité → Clé privée

⚠️ **IMPORTANT**: Ne JAMAIS partager ta private_key !

### 🤖 Auto-Trading

```json
{
  "auto_trading": {
    "enabled": false,              // true = LIVE, false = désactivé
    "position_size_usd": 100,      // Taille de chaque position ($)
    "max_concurrent_positions": 1, // Nombre max (1 = TOP 1 seulement)
    "min_profit_per_snipe": 5.0,   // Profit minimum requis ($)
    "use_limit_orders": true,      // Ordres LIMIT (obligatoire)
    "slippage_tolerance": 0.001    // 0.1% slippage max
  }
}
```

**Recommandations**:
- `enabled: false` pour DRY-RUN d'abord
- `position_size_usd: 100` pour débuter
- `max_concurrent_positions: 1` (TOP 1 seulement)
- `min_profit_per_snipe: 5.0` minimum raisonnable

### 📊 Monitoring

```json
{
  "monitoring": {
    "log_level": "INFO"  // DEBUG pour plus de détails
  }
}
```

**Niveaux**:
- `DEBUG`: Tous les détails
- `INFO`: Actions principales (recommandé)
- `WARNING`: Alertes seulement
- `ERROR`: Erreurs uniquement

---

## 🔄 Pourquoi 2 fichiers config ?

### config.simple.json (ou config.example.json)

- ✅ Template propre
- ✅ Valeurs par défaut
- ✅ À copier pour créer ta config
- ✅ **Peut être commité sur Git** (pas de secrets)

### config.json

- ⚠️ **TA config réelle**
- ⚠️ Contient tes clés privées
- ❌ **JAMAIS commiter sur Git** (dans `.gitignore`)
- 🔒 Garder sécurisé

**Principe**:
```
config.simple.json (template)
        ↓ copier
config.json (ta config)
        ↓ ajouter tes clés
Prêt ! 🚀
```

---

## 🛡️ Sécurité

### ✅ À faire

- ✅ Copier le template → `config.json`
- ✅ Remplir tes clés dans `config.json`
- ✅ Vérifier que `.gitignore` contient `config.json`
- ✅ Tester en DRY-RUN d'abord (`enabled: false`)

### ❌ À NE JAMAIS faire

- ❌ Commiter `config.json` sur Git
- ❌ Partager ta `private_key`
- ❌ Mettre tes clés dans `config.example.json`
- ❌ Activer LIVE sans tester DRY-RUN

---

## 📋 Configuration Avancée (Optionnel)

Si tu veux plus de contrôle, utilise `config.example.json` qui contient:

```json
{
  "wallet": { ... },
  "auto_trading": { ... },
  "exchanges": {
    "extended": { ... },
    "hyperliquid": { ... }
  },
  "trading": {
    "max_leverage": 5,
    "use_tp_sl": true
  },
  "monitoring": {
    "enable_dashboard": true,
    "dashboard_port": 8050
  }
}
```

**Mais pour le bot auto, `config.simple.json` suffit ! 👍**

---

## 🔍 Vérifier ta Config

### Commande

```powershell
# Afficher ta config (masque les clés)
py -c "import json; config=json.load(open('config/config.json')); print('Wallet:', config['wallet']['address'][:10]+'...'); print('Auto-trading:', config['auto_trading']['enabled'])"
```

### Devrait afficher

```
Wallet: 0x1234abcd...
Auto-trading: False
```

---

## ❓ FAQ

**Q: Pourquoi ma config actuelle a "FROM_ENV_..." ?**  
A: Ancienne version qui lisait depuis variables d'environnement. Utilise `config.simple.json` maintenant !

**Q: Pourquoi il y a des paires "BTC/USDT" en dur ?**  
A: Pour l'ancien mode "manual". Le bot auto scanne TOUT, pas besoin de paires !

**Q: Je dois remplir "exchanges" ?**  
A: Non ! Le bot auto-trading utilise les APIs directement. Juste wallet + auto_trading.

**Q: C'est sûr de mettre ma clé privée dans un fichier ?**  
A: Oui SI le fichier est dans `.gitignore` et sur ton PC personnel. Ne JAMAIS partager.

---

## ✅ Checklist

- [ ] `config.simple.json` copié → `config.json`
- [ ] Wallet address remplie
- [ ] Private key remplie
- [ ] `auto_trading.enabled = false` (DRY-RUN)
- [ ] `position_size_usd` défini
- [ ] `.gitignore` contient `config.json`

**Prêt à lancer ! 🚀**

---

## 🎯 Résumé Ultra-Rapide

```powershell
# 1. Copier
cp config\config.simple.json config\config.json

# 2. Éditer
notepad config\config.json

# 3. Remplir
# - wallet.address
# - wallet.private_key
# - auto_trading.enabled (false pour test)

# 4. Lancer
py bot_auto_trading.py
```

**C'est tout ! Simple et sécurisé. 👍**

---

**Créé le: 14 Novembre 2025**  
**Fichier recommandé: `config.simple.json`**  
**Status: ✅ Simplifié**
