# 🎯 FOCUS EXTENDED + VARIATIONAL UNIQUEMENT

## ✅ Modifications Effectuées

Le bot a été reconfiguré pour se concentrer **UNIQUEMENT** sur Extended et Variational, conformément au PDF original.

### 📊 Avant vs Après

| Aspect | Avant | Après |
|--------|-------|-------|
| **Exchanges analysés** | 26 exchanges (4 x 1h + 22 x 8h) | **2 exchanges** (Extended + Variational) |
| **Source données** | Loris Tools (tous exchanges) | Loris Tools (Extended + Variational filtré) |
| **Opportunités trouvées** | 72 opportunités | 23 opportunités |
| **Complexité** | Chercher parmi 26 exchanges | Direct Extended vs Variational |

---

## 📝 Fichiers Modifiés

### 1️⃣ `src/data/loris_api.py`

**Changement dans `find_best_arbitrage()`:**
- ❌ Avant: Cherchait parmi tous les exchanges disponibles
- ✅ Après: Cherche **uniquement Extended et Variational**

```python
# Nouveau code
for exchange_name, info in exchanges_info.items():
    base_name = exchange_name.split('_')[0].lower()
    
    # Extended (1h)
    if base_name == 'extended':
        extended_rate = self.get_funding_rate(data, exchange_name, symbol)
    
    # Variational (8h)
    elif base_name == 'variational':
        variational_rate = self.get_funding_rate(data, exchange_name, symbol)
```

**Changement dans `get_extended_like_exchanges()` et `get_variational_like_exchanges()`:**
- ❌ Avant: Retournait tous les exchanges 1h ou 8h
- ✅ Après: Retourne **uniquement Extended ou Variational**

---

### 2️⃣ `src/data/funding_collector.py`

**Changement dans `_fetch_extended_funding()` et `_fetch_variational_funding()`:**
- ❌ Avant: Cherchait parmi Hyperliquid, Lighter, Vest, Binance, Bybit, OKX, etc.
- ✅ Après: Cherche **uniquement Extended ou Variational**

```python
# Nouveau code pour Extended
for exchange_name, info in exchanges_info.items():
    if exchange_name.split('_')[0].lower() == 'extended':
        rate = self.loris.get_funding_rate(data, exchange_name, base_symbol)
        if rate is not None:
            logger.debug(f"Extended funding for {base_symbol}: {rate:.6f}")
            return rate
```

---

### 3️⃣ `find_best_opportunity.py`

**Changements:**
- ❌ Avant: Scannait 26 exchanges et prenait les meilleurs rates
- ✅ Après: Utilise **uniquement Extended et Variational**

```python
# Chercher Extended et Variational
extended_exchange = None
variational_exchange = None

for exchange_name in exchanges_info.keys():
    base = exchange_name.split('_')[0].lower()
    if base == 'extended':
        extended_exchange = exchange_name
    elif base == 'variational':
        variational_exchange = exchange_name

# Puis pour chaque symbole
extended_rate = loris.get_funding_rate(data, extended_exchange, symbol)
variational_rate = loris.get_funding_rate(data, variational_exchange, symbol)
```

---

### 4️⃣ Nouveau fichier: `explain_calculs_v2.py`

**Script d'explication mis à jour:**
- ✅ Affiche clairement "Extended vs Variational uniquement"
- ✅ Ne cherche pas parmi d'autres exchanges
- ✅ Timeline simplifiée avec les 2 DEX

---

## 🧪 Résultats des Tests

### Test 1: Scanner les opportunités

```bash
py find_best_opportunity.py 5
```

**Résultat:**
```
📊 Exchanges utilisés:
   Extended (1h):    extended_1_perp
   Variational (8h): variational_1_perp

✅ Analyse terminée: 23 opportunités trouvées

🏆 TOP 5 OPPORTUNITÉS D'ARBITRAGE
┌─────┬───────────┬───────────┬───────────┬──────────┬─────────────┬───────────┬───────────────┬──────────┐
│   # │ Symbole   │   Rate 1h │   Rate 8h │   Spread │ Profit 8h   │ $/heure   │ Type          │ Risque   │
├─────┼───────────┼───────────┼───────────┼──────────┼─────────────┼───────────┼───────────────┼──────────┤
│   1 │ AVNT      │  -0.00059 │  -0.00025 │  0.00034 │ $44.70      │ $5.90     │ both_negative │ medium   │
│   2 │ APT       │  -0.00028 │  -0.00038 │  0.0001  │ $18.60      │ $2.80     │ both_negative │ medium   │
│   3 │ ENA       │  -0.00023 │  -0.00025 │  2e-05   │ $15.90      │ $2.30     │ both_negative │ medium   │
│   4 │ BNB       │  -0.00022 │  -9e-05   │  0.00013 │ $16.70      │ $2.20     │ both_negative │ medium   │
│   5 │ BERA      │   0.0001  │  -0.00063 │  0.00073 │ $14.30      │ $1.79     │ mixed         │ low      │
└─────┴───────────┴───────────┴───────────┴──────────┴─────────────┴───────────┴───────────────┴──────────┘
```

### Test 2: Explication détaillée

```bash
py explain_calculs_v2.py AVNT
```

**Résultat:**
```
🔍 Récupération des funding rates:
   ✅ Extended (1h):    -0.000590
   ✅ Variational (8h): -0.000240

🎯 STRATÉGIE: Both Negative
LONG EXTENDED @ -0.000590 (négatif → on REÇOIT)
SHORT VARIATIONAL @ -0.000240 (négatif → on REÇOIT aussi)

▶️  Option B: EARLY CLOSE (fermer à 7h avant Variational) ⭐
   Extended:     7 paiements × $5.90 = +$41.30
   Variational:  0 paiement (fermé avant!) = $0.00
   TOTAL:        $41.30
   Par heure:    $5.90/h ← MEILLEUR!
```

---

## 🎯 Ce qui correspond maintenant au PDF

✅ **Point 1**: Delta-neutral entre Extended et Variational  
✅ **Point 2**: Funding rates en temps réel via Loris Tools  
✅ **Point 3**: Timing arbitrage 1h vs 8h  
✅ **Point 4**: Early close avant le paiement Variational  
✅ **Point 5**: Comparaison full_cycle vs early_close  
✅ **Point 6**: Surveillance polarité (déjà implémenté)  
✅ **Point 7**: Vérification intervalle Variational (déjà implémenté)  
✅ **Point 8**: Margin importante vs petit levier (déjà implémenté)  
✅ **Point 9**: Ouverture synchronisée même prix (déjà implémenté)  
✅ **Point 10**: TP/SL protection (déjà implémenté)  

---

## 🚀 Utilisation

### Scanner les meilleures opportunités Extended/Variational

```bash
py find_best_opportunity.py 10
```

### Voir les calculs détaillés pour un symbole

```bash
py explain_calculs_v2.py AVNT
py explain_calculs_v2.py BNB
py explain_calculs_v2.py APT
```

### Lancer le bot (mode auto)

```bash
py src\main.py
```

Le bot va:
1. Récupérer les funding rates Extended et Variational via Loris Tools
2. Scanner les 1428 symboles disponibles
3. Calculer les opportunités entre Extended et Variational uniquement
4. Ouvrir les trades delta-neutral les plus rentables
5. Fermer automatiquement avant le paiement Variational si nécessaire

---

## 📌 Configuration

Les clés API pour Extended et Variational sont dans `config/config.json`:

```json
{
  "exchanges": {
    "extended": {
      "name": "Extended",
      "api_key": "YOUR_EXTENDED_API_KEY",
      "api_secret": "YOUR_EXTENDED_API_SECRET",
      "funding_interval": 3600
    },
    "variational": {
      "name": "Variational",
      "api_key": "YOUR_VARIATIONAL_API_KEY",
      "api_secret": "YOUR_VARIATIONAL_API_SECRET",
      "funding_intervals": {
        "default": 28800
      }
    }
  }
}
```

**⚠️ Important:** Remplacer `YOUR_EXTENDED_API_KEY` et `YOUR_VARIATIONAL_API_KEY` par vos vraies clés API.

---

## 📊 Comparaison Performance

### Avant (26 exchanges)
- 72 opportunités trouvées
- Meilleure: ARK @ $67.30/h (Hyperliquid vs Bybit)
- Top 5: $170.20/h
- Top 10: $213.32/h

### Après (Extended + Variational uniquement)
- 23 opportunités trouvées
- Meilleure: AVNT @ $5.90/h (Extended vs Variational)
- Top 5: $14.99/h
- Top 10: $21.98/h

**Conclusion:**
- Moins d'opportunités (23 vs 72)
- Profits plus modestes mais **conformes au PDF**
- Focus sur vos wallets Extended et Variational existants
- Pas de dispersion sur 24 autres exchanges

---

## ✅ Résumé

Le bot est maintenant **100% aligné avec le PDF**:
- ✅ Extended (1h) vs Variational (8h)
- ✅ Données Loris Tools en temps réel
- ✅ 2 DEX uniquement (vos wallets)
- ✅ Timing arbitrage comme décrit
- ✅ Toutes les fonctionnalités avancées conservées

Prêt à trader avec vos wallets Extended et Variational ! 🚀
