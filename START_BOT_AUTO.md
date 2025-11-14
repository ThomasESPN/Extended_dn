# ⚡ QUICK START - Bot Auto-Trading

## 🚀 Lancement Rapide (3 étapes)

### 1️⃣ Configuration (2 minutes)

```powershell
# Copier le template
cp config\config.example.json config\config.json

# Éditer avec vos clés
notepad config\config.json
```

**Éditer ces lignes**:
```json
{
  "wallet": {
    "address": "0xVOTRE_WALLET_ADDRESS",
    "private_key": "VOTRE_PRIVATE_KEY"
  },
  "auto_trading": {
    "enabled": true,
    "position_size_usd": 100
  }
}
```

### 2️⃣ Test DRY-RUN (OBLIGATOIRE)

```powershell
py bot_auto_trading.py
# Choisir 1 (DRY-RUN)
```

✅ **Laisse tourner 24h** pour valider la logique

### 3️⃣ Mode LIVE (Quand prêt)

```powershell
py bot_auto_trading.py
# Choisir 2 (LIVE)
# Taper "CONFIRM"
```

⚠️ **AVANT**: Vérifie wallet, fonds, teste DRY-RUN 24h+

---

## 📊 Ce que fait le bot

```
12:50 - Scan → Trouve TOP 1 (ex: IP, $26.80/snipe)
12:55 - Ouvre LONG Extended + SHORT Hyperliquid ($100 des 2 côtés)
13:00 - Reçoit funding Extended
13:05 - Ferme tout
Durée: 10 min | Profit: $2.68 sur $100
```

**21 cycles/jour** (évite 3 cycles HL) = **$42-210/jour** sur $100

---

## ⚙️ Configuration Essentielle

| Paramètre | Valeur | Description |
|-----------|--------|-------------|
| `enabled` | `true` | Active le bot |
| `position_size_usd` | `100` | Taille position |
| `max_concurrent_positions` | `1` | Trade TOP 1 |
| `min_profit_per_snipe` | `5.0` | Profit minimum |

---

## ✅ Checklist

**Avant DRY-RUN**:
- [ ] Config créée avec wallet
- [ ] `enabled: true`
- [ ] `position_size_usd` défini

**Avant LIVE**:
- [ ] DRY-RUN testé 24h+
- [ ] Wallet vérifié
- [ ] Fonds suffisants (3x position)
- [ ] Commence petit ($100-500)

---

## 🛡️ Sécurité

✅ Delta-neutral = Pas de risque de prix  
✅ Ordres LIMIT = Size identique  
✅ 10 min de risque par cycle  
✅ Évite cycles HL 8h  
✅ Logs détaillés  

---

## 📖 Documentation Complète

- `IMPLEMENTATION_FINALE.md` - Résumé complet
- `BOT_AUTO_TRADING_GUIDE.md` - Guide détaillé
- `README.md` - Vue d'ensemble
- `WALLET_SETUP.md` - Config wallet

---

## 🆘 Problème ?

```powershell
# Tester API
py test_loris.py

# Scanner opportunités
py find_best_opportunity.py 10

# Voir logs
Get-Content logs\bot_auto_*.log -Tail 50
```

---

**🚀 Prêt ! Commence par DRY-RUN 24h puis LIVE quand confiant !**

*Bot: `bot_auto_trading.py` | Config: `config/config.json`*
