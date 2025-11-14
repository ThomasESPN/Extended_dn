# 🎯 CONFIG - RÉPONSE SIMPLE

## ❓ TA QUESTION

> "Pourquoi y a min_profit et tout maintenant ? C'était pas bon dans le config.json ??"

## ✅ RÉPONSE SIMPLE

**Ces paramètres SONT nécessaires** parce que le bot doit savoir:

1. **`enabled`** → Je trade ou pas ?
2. **`position_size_usd`** → Combien $ je mets ?
3. **`max_concurrent_positions`** → Combien de positions en même temps ?
4. **`min_profit_per_snipe`** → À partir de combien $ de profit je trade ?

---

## 💡 EXEMPLE CONCRET

### Sans `min_profit_per_snipe`

```
Scan trouve:
- IP: $26.80/snipe    → Trade ✅
- ZORA: $6.75/snipe   → Trade ✅
- ENA: $1.27/snipe    → Trade ✅
- TAO: $0.19/snipe    → Trade ✅ ← PROBLÈME !
```

**Résultat**: Bot trade de la merde à $0.19 → Frais > Profit = **PERTE** ❌

### Avec `min_profit_per_snipe: 5.0`

```
Scan trouve:
- IP: $26.80/snipe    → Trade ✅ (> $5)
- ZORA: $6.75/snipe   → Trade ✅ (> $5)
- ENA: $1.27/snipe    → SKIP ❌ (< $5)
- TAO: $0.19/snipe    → SKIP ❌ (< $5)
```

**Résultat**: Bot trade SEULEMENT les bonnes opportunités = **PROFIT** ✅

---

## 🎯 CONFIG PARFAITE

```json
{
  "wallet": {
    "address": "0xTON_WALLET",
    "private_key": "TA_CLE"
  },
  "auto_trading": {
    "enabled": false,              
    "position_size_usd": 100,      
    "max_concurrent_positions": 1, 
    "min_profit_per_snipe": 5.0    
  }
}
```

**4 paramètres = Tout ce dont le bot a besoin !**

---

## 📋 CE QUE CHAQUE PARAMÈTRE FAIT

| Paramètre | Ça fait quoi ? | Valeur recommandée |
|-----------|----------------|-------------------|
| `enabled` | Active/désactive le trading | `false` pour test |
| `position_size_usd` | Taille de chaque position | `100` pour débuter |
| `max_concurrent_positions` | Combien de trades en même temps | `1` (TOP 1) |
| `min_profit_per_snipe` | Profit minimum pour trader | `5.0` (évite merde) |

---

## 🔥 RÉSUMÉ

**Tu avais raison**: J'avais trop simplifié !

**Solution**: Config avec les **4 paramètres essentiels**

**Fichier à utiliser**: `config/config.bot_auto.json`

```powershell
# Copier
cp config\config.bot_auto.json config\config.json

# Éditer
notepad config\config.json

# Remplir wallet + ajuster paramètres

# Lancer
py bot_auto_trading.py
```

**C'est tout ! 🚀**

---

**Les paramètres SONT nécessaires pour que le bot trade intelligemment ! 👍**
