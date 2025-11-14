# 🔐 CONFIG WALLET - RÉPONSE À TES QUESTIONS

**Date**: 14 Novembre 2025

---

## ❓ TES QUESTIONS

### 1. "La config des wallet est où ?"

**Réponse**: Dans `config/config.json`

```
config/
├── config.simple.json    ← ✨ Template ultra-simple (NOUVEAU)
├── config.example.json   ← Template complet (ancien)
└── config.json           ← TA CONFIG (à créer, avec tes clés)
```

---

### 2. "Pourquoi y a un fichier config.example ET un fichier config ?"

**Réponse**: Sécurité Git !

```
config.example.json → Template PROPRE (peut être sur Git)
         ↓ Tu copies
config.json → TA CONFIG avec clés (JAMAIS sur Git)
```

**Pourquoi ?**
- `config.example.json` = Template sans secrets → Safe pour Git ✅
- `config.json` = Tes vraies clés → **DANGEREUX sur Git** ❌

**Protection**: `config.json` est dans `.gitignore` = **ne sera JAMAIS uploadé sur GitHub**

---

### 3. "Pourquoi y a des paires en dur (BTC/USDT, ETH/USDT) ?"

**Réponse**: C'est pour l'ANCIEN mode "manual" !

**Ancien système** (src/main.py):
```json
{
  "pairs": ["BTC/USDT", "ETH/USDT"]  // Mode manual
}
```
→ Le bot surveillait SEULEMENT ces paires

**NOUVEAU bot auto-trading** (`bot_auto_trading.py`):
```python
# Scanne TOUTES les paires automatiquement (1430+)
# PAS BESOIN de liste de paires !
```

**Tu peux les ignorer** si tu utilises `bot_auto_trading.py` ! 👍

---

## ✅ SOLUTION SIMPLE

J'ai créé **`config/config.simple.json`** avec SEULEMENT ce dont tu as besoin:

```json
{
  "wallet": {
    "address": "YOUR_WALLET_ADDRESS_HERE",
    "private_key": "YOUR_PRIVATE_KEY_HERE"
  },
  "auto_trading": {
    "enabled": false,
    "position_size_usd": 100,
    "max_concurrent_positions": 1,
    "min_profit_per_snipe": 5.0
  }
}
```

**Pas de paires en dur ! Pas de trucs compliqués !**

---

## 🚀 COMMENT CONFIGURER (3 ÉTAPES)

### Étape 1: Copier le template simple

```powershell
cd config
cp config.simple.json config.json
```

### Étape 2: Éditer

```powershell
notepad config.json
```

### Étape 3: Remplir SEULEMENT 2 choses

```json
{
  "wallet": {
    "address": "0xTON_WALLET",      // ← Remplace ici
    "private_key": "TA_CLE_PRIVEE"  // ← Et ici
  },
  "auto_trading": {
    "enabled": true  // false = DRY-RUN, true = LIVE
  }
}
```

**C'est tout ! Le reste utilise les valeurs par défaut.**

---

## 🔍 COMPARAISON DES CONFIGS

### config.simple.json (✨ NOUVEAU - Recommandé)

```json
{
  "wallet": { ... },
  "auto_trading": { ... }
}
```
**Avantages**:
- ✅ Ultra-simple (5 lignes)
- ✅ Seulement l'essentiel
- ✅ Pas de paires en dur
- ✅ Parfait pour bot auto

### config.example.json (Ancien - Complet)

```json
{
  "wallet": { ... },
  "auto_trading": { ... },
  "exchanges": { ... },
  "trading": { ... },
  "pairs": ["BTC/USDT", "ETH/USDT"]  // ← Pour mode manual
}
```
**Avantages**:
- Plus de contrôle
- Pour mode manual/smart
- Config avancée

**Utilise `config.simple.json` sauf si tu veux l'ancien système !**

---

## 🛡️ SÉCURITÉ

### ✅ Ce qui est safe sur Git

```
config/config.simple.json   ✅ Pas de secrets
config/config.example.json  ✅ Pas de secrets
README.md                   ✅ Pas de secrets
```

### ❌ Ce qui n'est JAMAIS sur Git

```
config/config.json  ❌ Contient tes clés privées !
.env                ❌ Variables sensibles
```

**Protection automatique**: `.gitignore` bloque ces fichiers

---

## 🎯 RÉSUMÉ RAPIDE

**Question 1**: Où est la config wallet ?  
→ `config/config.json` (à créer depuis `config.simple.json`)

**Question 2**: Pourquoi 2 fichiers ?  
→ Sécurité Git (template vs config réelle)

**Question 3**: Pourquoi des paires en dur ?  
→ Ancien mode manual, **pas besoin pour bot auto** !

---

## 📋 CHECKLIST

- [ ] Lire `CONFIG_GUIDE.md` (ce fichier)
- [ ] Copier `config.simple.json` → `config.json`
- [ ] Remplir wallet address + private key
- [ ] Vérifier `.gitignore` (déjà fait ✅)
- [ ] Lancer bot avec ta config

---

## 🆘 SI PROBLÈME

### "FROM_ENV_..." dans ma config

```powershell
# Remplacer par la config simple
cp config\config.simple.json config\config.json
notepad config\config.json
```

### "Pas de wallet dans config"

```json
// Ajouter en haut du fichier
{
  "wallet": {
    "address": "0xTON_WALLET",
    "private_key": "TA_CLE"
  }
}
```

### "Bot dit config invalide"

```powershell
# Vérifier la syntaxe JSON
py -c "import json; json.load(open('config/config.json'))"
```

---

## 📄 DOCS CRÉÉES

1. **`config/config.simple.json`** ✨ - Template ultra-simple
2. **`CONFIG_GUIDE.md`** - Guide complet de configuration
3. **`.gitignore`** ✅ - Mis à jour avec avertissement

---

**Maintenant tu comprends ! Utilise `config.simple.json` et c'est tout bon ! 🚀**

---

**Créé le**: 14 Novembre 2025  
**Fichier recommandé**: `config/config.simple.json`  
**Status**: ✅ EXPLIQUÉ ET SIMPLIFIÉ
