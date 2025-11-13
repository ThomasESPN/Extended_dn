# 📊 EXPLICATION DÉTAILLÉE DES CALCULS - Exemple ARK

## ❓ Ta Question

> "Comment tu calcules ? Le checker est sur nos deux DEX uniquement ?"

**Réponse**: Non ! Le système utilise **Loris Tools** qui agrège 26 exchanges.

Pour chaque symbole, on cherche:
- **Meilleur rate 1h** parmi 4 exchanges (Extended, Hyperliquid, Lighter, Vest)
- **Meilleur rate 8h** parmi 22 exchanges (Binance, Bybit, OKX, Kucoin, etc.)

Ensuite on calcule le profit d'arbitrage entre ces deux meilleurs rates.

---

## 🎯 Exemple Concret: ARK

### Données Récupérées (Loris Tools)

```
Symbole: ARK
Position size: $10,000

Extended (1h):  -0.005890  (on REÇOIT si on est LONG)
Variational (8h): -0.008810  (on REÇOIT si on est SHORT)

Type: both_negative ← Les DEUX négatifs!
```

---

## 🧮 CALCULS DÉTAILLÉS

### Étape 1️⃣: Calcul des Paiements Unitaires

```python
# Formule: Payment = Position_Size × Funding_Rate

# Extended (1h):
ext_payment = 10000 × abs(-0.005890)
ext_payment = 10000 × 0.005890
ext_payment = $58.90 par paiement

# Variational (8h):
var_payment = 10000 × abs(-0.008810)
var_payment = 10000 × 0.008810
var_payment = $88.10 par paiement
```

### Étape 2️⃣: Nombre de Paiements sur 8h

```python
# Intervalle Extended: 1h (3600s)
# Intervalle Variational: 8h (28800s)

num_ext_payments = 28800 / 3600 = 8 paiements

# Timeline sur 8h:
# 00h → Extended paie
# 01h → Extended paie
# 02h → Extended paie
# 03h → Extended paie
# 04h → Extended paie
# 05h → Extended paie
# 06h → Extended paie
# 07h → Extended paie
# 08h → Extended + Variational paient
```

### Étape 3️⃣: Stratégie "Both Negative"

**Position**:
- **LONG** sur Extended → On **REÇOIT** le funding (car négatif)
- **SHORT** sur Variational → On **REÇOIT** le funding (car négatif)

**Deux Options**:

#### Option A: Full Cycle (garder 8h complètes)
```python
# On reçoit les 8 paiements Extended
profit_extended = 58.90 × 8 = $471.20

# Mais on PAIE 1 fois Variational à la fin
# (car on est SHORT et le funding est négatif)
profit_variational = -88.10

# TOTAL:
profit_full_cycle = 471.20 - 88.10 = $383.10
profit_per_hour = 383.10 / 8 = $47.89/h
```

#### Option B: Early Close (fermer AVANT Variational) ⭐
```python
# On ferme 1h AVANT le paiement Variational (à 7h)
# Donc on reçoit seulement 7 paiements Extended

profit_extended = 58.90 × 7 = $412.30

# On ne paie PAS Variational (on a fermé avant!)
profit_variational = $0

# TOTAL:
profit_early_close = 412.30 - 0 = $412.30
profit_per_hour = 412.30 / 7 = $58.90/h ← MEILLEUR!
```

**Le bot choisit automatiquement "early_close" car:**
```python
if profit_early / hours_early > profit_full / hours_full:
    strategy = "early_close"  # $58.90/h > $47.89/h ✅
```

### Étape 4️⃣: Calcul Final Affiché

```
💰 OPPORTUNITÉ #1 - ARK
  Position size:     $10,000
  
  📈 LONG Extended @ -0.005890
     → On REÇOIT $58.90 par heure (8 fois sur 7h)
  
  📉 SHORT Variational @ -0.008810
     → On REÇOIT... mais on ferme avant!
  
  Cycle complet 8h:  $383.10  (si on reste 8h)
  Fermeture anticipée: $412.30  (si on ferme à 7h) ← Meilleur!
  Par heure:         $58.90/h  (412.30 / 7)
  
  🎯 Stratégie:      early_close
```

---

## 🔍 D'où Viennent les Rates ?

### Loris Tools API

```python
# Le système interroge https://api.loris.tools/funding
# Résultat pour ARK:

{
  "symbols": ["ARK", ...],
  "funding_rates": {
    "extended_1_perp": {      # Exchange 1h
      "ARK": -58.9            # × 10,000 par l'API
    },
    "hyperliquid_1_perp": {   # Exchange 1h
      "ARK": -62.3
    },
    "binance_1_perp": {       # Exchange 8h
      "ARK": -88.1
    },
    "bybit_1_perp": {         # Exchange 8h
      "ARK": -90.5
    },
    ...
  }
}
```

**Le bot sélectionne**:
1. **Meilleur 1h** pour ARK → Extended @ -0.00589 (le moins négatif = moins on paie)
2. **Meilleur 8h** pour ARK → Binance @ -0.00881 (le moins négatif = moins on paie)

⚠️ **Note**: L'API Loris multiplie par 10,000, donc:
- API renvoie: `-58.9`
- Rate réel: `-58.9 / 10000 = -0.00589`

---

## 📈 Pourquoi "Both Negative" est Rentable ?

### Concept Clé

**Quand funding est NÉGATIF**:
- Si tu es **LONG** → Tu **REÇOIS** l'argent
- Si tu es **SHORT** → Tu **PAIES** l'argent

**MAIS** avec le timing funding arbitrage:

```
Position LONG Extended (funding négatif -0.00589)
→ On REÇOIT 8 fois sur 7h = +$412.30

Position SHORT Variational (funding négatif -0.00881)
→ On FERME avant le paiement = $0 à payer

PROFIT NET = $412.30 sur 7h = $58.90/h
```

**C'est comme récolter les fruits Extended 7 fois, puis partir avant de devoir payer Variational !**

---

## 🎨 Timeline Visuelle ARK

```
Heure    Extended (1h)    Variational (8h)    Action
────────────────────────────────────────────────────────────
00:00    +$58.90          -                   ✅ Reçu
01:00    +$58.90          -                   ✅ Reçu
02:00    +$58.90          -                   ✅ Reçu
03:00    +$58.90          -                   ✅ Reçu
04:00    +$58.90          -                   ✅ Reçu
05:00    +$58.90          -                   ✅ Reçu
06:00    +$58.90          -                   ✅ Reçu
──────── ─────────────────────────────────────────────────
07:00    -                -                   🚪 ON FERME!
──────── ─────────────────────────────────────────────────
08:00    +$58.90          -$88.10             ❌ Évité!

TOTAL:   7 × $58.90 = $412.30
         Sur 7h = $58.90/h
```

---

## 🔄 Comparaison avec "Standard" (ARK vs ASML)

### ARK (both_negative) - $58.90/h
```
Extended: -0.00589 (on REÇOIT)
Variational: -0.00881 (on REÇOIT si on reste, on ÉVITE si on part)
→ Stratégie: Partir avant Variational
```

### ASML (standard) - $7.17/h
```
Extended: +0.00073 (on PAIE)
Variational: +0.00010 (on PAIE)
→ Stratégie: Arbitrage de différentiel classique
→ Moins rentable car on PAIE des deux côtés
```

---

## 📊 Résumé des 4 Stratégies

### 1. Standard
```
Extended: +  Variational: -
ou
Extended: -  Variational: +

→ Un positif, un négatif
→ Profit sur le spread
```

### 2. Both Positive
```
Extended: +0.001  Variational: +0.003

→ Les deux positifs
→ Long sur le plus faible, Short sur le plus élevé
→ Profit = différence
```

### 3. Both Negative ⭐ (LE MEILLEUR)
```
Extended: -0.00589  Variational: -0.00881

→ Les deux négatifs
→ On REÇOIT des deux (si on gère le timing)
→ Fermer avant Variational pour maximiser
→ ARK: $58.90/h
```

### 4. Mixed
```
Situations spéciales et asymétries
```

---

## ✅ RÉPONSE À TA QUESTION

### "Le checker est sur nos deux DEX uniquement ?"

**NON !** Le système check **26 exchanges** via Loris Tools:

**Exchanges 1h** (4):
- Extended
- Hyperliquid
- Lighter
- Vest

**Exchanges 8h** (22):
- Binance
- Bybit
- OKX
- Kucoin
- BingX
- Bitget
- ... (16 autres)

**Pour chaque symbole**, on:
1. Trouve le **meilleur rate 1h** parmi les 4
2. Trouve le **meilleur rate 8h** parmi les 22
3. Calcule le profit d'arbitrage entre ces deux
4. Trie par profit/heure décroissant

---

## 💡 Pourquoi ARK est #1 ?

```python
# ARK
profit_per_hour = $58.90/h
type = "both_negative"
→ On REÇOIT des deux côtés (stratégie optimale)

# DOOD (#2)
profit_per_hour = $41.80/h
type = "both_negative"
→ Moins de différence entre Extended/Variational

# ASML (#10)
profit_per_hour = $7.17/h
type = "standard"
→ Arbitrage classique, moins rentable
```

---

## 🎯 Code Source

```python
# src/strategies/arbitrage_calculator.py - ligne 231

def _strategy_both_negative(
    self, symbol, ext_rate, var_rate, ext_payment, var_payment,
    ext_interval, var_interval
):
    """Both negative: Fermer avant Variational"""
    
    num_ext_payments = var_interval // ext_interval  # 8
    
    # Profit si on ferme AVANT Variational (7 paiements)
    profit_early = ext_payment * (num_ext_payments - 1)
    # = 58.90 × 7 = $412.30
    
    # Profit si on garde tout le cycle (8 paiements - 1 Variational)
    profit_full = (ext_payment * num_ext_payments) - var_payment
    # = (58.90 × 8) - 88.10 = $383.10
    
    # Profit par heure (early close)
    profit_per_hour = profit_early / ((var_interval - 3600) / 3600)
    # = 412.30 / 7 = $58.90/h
    
    return ArbitrageOpportunity(
        profit_per_hour=58.90,
        recommended_strategy="early_close"
    )
```

---

## 🚀 Utilisation

```powershell
# Voir les calculs en temps réel
py find_best_opportunity.py 10

# Le bot choisit automatiquement la stratégie optimale:
# - Full cycle si plus rentable
# - Early close si meilleur (cas ARK)
```

---

**Voilà ! Les calculs sont basés sur 26 exchanges via Loris Tools, pas seulement Extended/Variational ! 🎯**
