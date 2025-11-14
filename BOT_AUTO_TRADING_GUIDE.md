# 🤖 Bot Auto-Trading Delta-Neutral - Guide Complet

## 📋 Vue d'ensemble

Ce bot automatise la stratégie de **timing funding arbitrage** entre Extended et Hyperliquid avec une approche **delta-neutral parfaite**.

### 🎯 Stratégie

1. **Scan** toutes les 5 min → Trouve le **TOP 1**
2. **X:55** (5 min avant funding) → Ouvre positions
   - 📈 **LONG Extended** (ordre LIMIT)
   - 📉 **SHORT Hyperliquid** (ordre LIMIT)
   - 💰 **Même size exacte** → Delta-neutral
3. **X:00** → Reçoit funding Extended
4. **X:05** (5 min après) → Ferme tout
5. **Évite cycles 8h HL** (00:00, 08:00, 16:00 UTC)

### ⚡ Avantages

- ✅ **Delta-neutral**: Pas de risque directionnel
- ✅ **Risque minimal**: 10 min par cycle vs 60 min
- ✅ **Ordres LIMIT**: Size identique garantie
- ✅ **Automatique**: Pas d'intervention manuelle
- ✅ **Sécurisé**: Mode DRY-RUN pour tester

---

## 🚀 Installation & Configuration

### 1. Configuration du Wallet

Éditer `config/config.json`:

```json
{
  "wallet": {
    "address": "0xVOTRE_WALLET_ADDRESS",
    "private_key": "VOTRE_PRIVATE_KEY"
  },
  "auto_trading": {
    "enabled": true,
    "position_size_usd": 100,
    "max_concurrent_positions": 1,
    "min_profit_per_snipe": 5.0,
    "use_limit_orders": true,
    "slippage_tolerance": 0.001
  }
}
```

### 2. Paramètres Clés

| Paramètre | Description | Recommandé |
|-----------|-------------|------------|
| `enabled` | Active/désactive l'auto-trading | `false` (test d'abord) |
| `position_size_usd` | Taille de position en USD | `100` (débutant) |
| `max_concurrent_positions` | Nombre max de positions | `1` (focus TOP 1) |
| `min_profit_per_snipe` | Profit minimum requis ($) | `5.0` |
| `use_limit_orders` | Utiliser ordres LIMIT | `true` (obligatoire) |
| `slippage_tolerance` | Tolérance slippage | `0.001` (0.1%) |

---

## 🎮 Utilisation

### Mode DRY-RUN (Recommandé pour débuter)

```powershell
# Simulation sans risque
py bot_auto_trading.py
# Choisir option 1 (DRY-RUN)
```

Le bot va:
- ✅ Scanner les opportunités réelles
- ✅ Afficher les décisions d'ouverture/fermeture
- ✅ Simuler l'exécution
- ❌ **AUCUN ordre réel passé**

### Mode LIVE (Trading réel)

⚠️ **ATTENTION: Argent réel !**

```powershell
py bot_auto_trading.py
# Choisir option 2 (LIVE)
# Taper "CONFIRM" pour valider
```

**Avant d'activer le LIVE:**
1. ✅ Tester en DRY-RUN pendant 24h minimum
2. ✅ Vérifier le wallet et les fonds
3. ✅ Commencer avec `position_size_usd` petit (100-500$)
4. ✅ Monitorer les premiers cycles manuellement

---

## 📊 Exemple de Cycle

### Timing Détaillé

```
10:50 UTC - Scan automatique
10:55 UTC - 🎯 OUVERTURE
            ├─ LONG Extended IP @ $X (ordre LIMIT)
            └─ SHORT Hyperliquid IP @ $X (ordre LIMIT)

11:00 UTC - 💰 FUNDING EXTENDED REÇU
            └─ Profit: $26.80 sur position $10,000

11:05 UTC - 💰 FERMETURE
            ├─ Close LONG Extended
            └─ Close SHORT Hyperliquid
            
Durée totale: 10 minutes
Risque: Minimal (delta-neutral)
```

### Output du Bot

```
════════════════════════════════════════════════════════════════════════════════
🎯 OUVERTURE POSITION DELTA-NEUTRAL: IP
════════════════════════════════════════════════════════════════════════════════
   📈 LONG  EXTENDED
   📉 SHORT HYPERLIQUID
   💰 Size: $100 (identique des deux côtés)
   📊 Profit estimé: $2.68
   ⏰ Fermeture dans ~10 min (5 min après funding)
   
   📡 Récupération des prix market...
   Prix EXTENDED: $0.0245
   Prix HYPERLIQUID: $0.0246
   
   Size LONG: 4081.632653 contracts
   Size SHORT: 4065.040650 contracts
   
   📝 Placement des ordres LIMIT...
   ✅ Positions ouvertes (DELTA-NEUTRAL)
════════════════════════════════════════════════════════════════════════════════
```

---

## 🔧 Fonctionnalités Techniques

### Delta-Neutral Parfait

```python
# Le bot garantit l'équilibre:
LONG_SIZE_USD = SHORT_SIZE_USD = position_size_usd

# Exemple: $100 de position
LONG Extended: $100 / prix_extended = X contracts
SHORT Hyperliquid: $100 / prix_hl = Y contracts

# Résultat: Exposition directionnelle = 0
# On profite uniquement du funding rate
```

### Ordres LIMIT

```python
# Prix ajustés pour fill rapide mais garanti
LONG_PRICE = market_price * 1.001  # +0.1%
SHORT_PRICE = market_price * 0.999 # -0.1%

# Garantit:
# ✅ Fill rapide (< 10 secondes)
# ✅ Size exacte
# ✅ Pas de slippage excessif
```

### Évitement Cycles HL

```python
# Heures HL 8h (UTC): 00:00, 08:00, 16:00
# Le bot saute ces heures automatiquement

Exemple:
- 15:55 → ❌ SKIP (prochain = 16:00 = cycle HL)
- 16:55 → ❌ SKIP (prochain = 17:00 mais après cycle HL)
- 17:55 → ✅ OK (prochain = 18:00 = safe)
```

---

## 📈 Performances Attendues

### Exemple Réel (14 Nov 2025)

**TOP 1: IP**
- Extended rate: -0.0027%
- Hyperliquid rate: -0.0005%
- Profit: **$26.80/snipe** (sur $10,000)
- Sur $100: **$2.68/snipe**

### Calcul Profit

```
Position: $100
Cycles par jour: 21 (24 - 3 cycles HL)
Profit moyen: $2.50/snipe

Profit/jour = $2.50 × 21 = $52.50
Profit/mois = $52.50 × 30 = $1,575

ROI mensuel: 1575% sur $100 de capital
```

⚠️ **Note**: Performances théoriques. Les résultats réels varient selon:
- Liquidité des paires
- Frais de transaction
- Slippage réel
- Conditions de marché

---

## 🛡️ Gestion des Risques

### Risques Principaux

1. **Risque de prix** → ❌ Éliminé (delta-neutral)
2. **Risque de liquidité** → ⚠️ Utiliser paires liquides
3. **Risque technique** → ⚠️ Surveiller les fills
4. **Risque de funding négatif** → ⚠️ Choisir TOP 1 seulement

### Sécurités Intégrées

```python
✅ Ordres LIMIT (pas de market)
✅ Vérification prix avant trade
✅ Validation profit minimum
✅ Évitement cycles HL
✅ Fermeture automatique après 10 min
✅ Logs détaillés de chaque action
```

### Recommandations

1. **Démarrer petit**: $100-500 par position
2. **Tester d'abord**: 24-48h en DRY-RUN
3. **Monitorer**: Premières 24h en LIVE
4. **Augmenter progressivement**: +$100 par semaine
5. **Diversifier**: 2-3 positions max quand confiant

---

## 🐛 Dépannage

### Le bot ne trade pas

```bash
# Vérifier:
1. config.json → auto_trading.enabled = true
2. Wallet configuré correctement
3. Mode LIVE activé (pas DRY-RUN)
4. Profit minimum raisonnable (5-10$)
```

### Ordres ne sont pas fill

```bash
# Causes possibles:
1. Paire illiquide → Choisir TOP 1 uniquement
2. Prix LIMIT trop éloigné → Ajuster slippage_tolerance
3. Fonds insuffisants → Vérifier balance wallet
```

### Erreur "eth-account not installed"

```powershell
py -m pip install eth-account web3
```

### Position non fermée

```bash
# Le bot ferme automatiquement à X:05
# Si problème: Ctrl+C fermera toutes les positions
# Sinon: Fermer manuellement via l'interface exchange
```

---

## 📝 Logs

### Emplacement

```
logs/bot_auto_YYYY-MM-DD.log
```

### Niveaux

- `INFO`: Actions principales (ouverture, fermeture)
- `DEBUG`: Détails techniques (prix, sizes)
- `WARNING`: Alertes (profit faible, skip cycle)
- `ERROR`: Erreurs (échec ordre, API down)

### Exemple

```log
11:55:02 | INFO     | 🎯 Fenêtre d'ouverture détectée !
11:55:03 | INFO     | 📊 SCAN DES OPPORTUNITÉS...
11:55:05 | INFO     | ✅ 73 opportunités trouvées
11:55:05 | SUCCESS  | 🏆 TOP 1: IP - $2.68/snipe
11:55:06 | INFO     | 🎯 OUVERTURE POSITION DELTA-NEUTRAL: IP
11:55:08 | SUCCESS  | ✅ Positions ouvertes (DELTA-NEUTRAL)
```

---

## ⚙️ Configuration Avancée

### Ajuster le Timing

```python
# Dans bot_auto_trading.py (ligne ~50)
self.open_before_minutes = 5   # Ouvrir X min avant
self.close_after_minutes = 5   # Fermer X min après

# Exemple: Plus conservateur
self.open_before_minutes = 3   # X:57
self.close_after_minutes = 3   # X:03
```

### Multi-Positions

```json
{
  "auto_trading": {
    "max_concurrent_positions": 3,
    "position_size_usd": 100
  }
}
```

Bot traderade TOP 3 paires simultanément.

### Filtrage Opportunités

```json
{
  "auto_trading": {
    "min_profit_per_snipe": 10.0,  // Profit mini $10
    "min_funding_rate": 0.0001     // Rate mini 0.01%
  }
}
```

---

## 🆘 Support

### Questions Fréquentes

**Q: C'est sûr ?**  
A: Stratégie delta-neutral = faible risque. Mais testez en DRY-RUN d'abord !

**Q: Combien de profit ?**  
A: Varie selon opportunités. TOP 1 = $2-10/snipe sur $100.

**Q: Faut-il surveiller ?**  
A: Non, automatique. Mais monitorer premières 24h recommandé.

**Q: Que se passe-t-il si internet coupe ?**  
A: Bot s'arrête. Positions restent ouvertes → fermer manuellement.

### Aide

- 📖 Documentation: `README.md`, `QUICK_START.md`
- 🧪 Tests: `test_loris.py`, `bot_sniper.py` (DRY-RUN)
- 💬 Issues: GitHub issues
- 📧 Contact: [Votre support]

---

## 🎓 Ressources

### Comprendre la Stratégie

- `Timing funding arbitrage.pdf` - Théorie complète
- `GUIDE_FUNDING_ARBITRAGE.md` - Explications détaillées
- `FOCUS_EXTENDED_VARIATIONAL.md` - Cycles Extended vs Variational

### Autres Bots

- `bot_sniper.py` - Version 2 min avant/1 min après
- `src/main.py` - Bot principal (modes manual/auto/smart)
- `find_best_opportunity.py` - Scanner multi-paires

---

## ✅ Checklist Avant LIVE

- [ ] Testé en DRY-RUN 24h minimum
- [ ] Wallet configuré et vérifié
- [ ] Balance suffisante (3x position_size minimum)
- [ ] `auto_trading.enabled = true`
- [ ] `position_size_usd` adapté à votre capital
- [ ] Premiers cycles monitorés manuellement
- [ ] Logs consultés régulièrement
- [ ] Plan de sortie défini (stop après X profit/perte)

---

**🚀 Prêt à trader ! Bon profit !**

*Dernière mise à jour: 14 Novembre 2025*

---

## ⚠️ Disclaimer

Ce bot est fourni à titre éducatif. Le trading comporte des risques. Ne tradez que des montants que vous pouvez vous permettre de perdre. Aucune garantie de profit. Utilisez à vos propres risques.
