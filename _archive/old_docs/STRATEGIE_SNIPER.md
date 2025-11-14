# 🎯 BOT SNIPER - STRATÉGIE ULTRA-OPTIMISÉE

## 🚀 **Découverte majeure : Extended paie au snapshot !**

Tu as testé : **Ouvrir à X:58 → Payé à X:00** ✅

Ça veut dire qu'Extended utilise un **snapshot** (photo instantanée) au moment du funding, pas une moyenne sur l'heure.

---

## 💡 **Avant vs Après :**

### ❌ **Ancienne stratégie (Hold 1h) :**
- 16:00 → Ouvrir LONG Extended + SHORT Hyperliquid
- 17:00 → Recevoir funding
- **Risque de prix : 60 MINUTES**

### ✅ **Nouvelle stratégie (Sniper 3min) :**
- 16:58 → Ouvrir LONG Extended + SHORT Hyperliquid
- 17:00 → Recevoir funding
- 17:01 → Fermer tout
- **Risque de prix : 3 MINUTES** (20x moins de risque !)

---

## 📊 **Exemple RESOLV :**

**Funding Extended : -0.1103% (on reçoit si LONG)**

### Stratégie Sniper :
- **16:58** → Ouvrir LONG Extended $10,000 + SHORT Hyperliquid $10,000
- **17:00** → Recevoir 0.1103% × $10,000 = **$11.03**
- **17:01** → Fermer tout

**Profit : $11.03**  
**Risque : 3 minutes**

### Sur 24h :
- **21 snipers** (évitant 00:00, 08:00, 16:00 UTC car cycles HL)
- **21 × $11.03 = $231.63 par jour** sur $10k
- **Risque total : 21 × 3 min = 63 minutes** (au lieu de 21h !)

---

## ⚠️ **CRITICAL : Delta-Neutral Perfect**

**TRÈS IMPORTANT :**

Pour que ça marche, les deux positions doivent avoir **EXACTEMENT** la même size :

- LONG Extended : $10,000
- SHORT Hyperliquid : $10,000

**Si les sizes sont différentes :**
- LONG $10,000 vs SHORT $9,500 → Tu as $500 de risque directionnel !
- Le prix bouge → Tu perds/gagnes sur les $500

**Solution :**
1. **Ordres LIMIT** (pas market) pour contrôler le prix exact
2. **Vérifier** que les deux ordres sont fill à la même size
3. **Fermer** immédiatement si les sizes diffèrent

---

## 🎯 **Timing optimal :**

### Ouverture : X:58
- 2 minutes avant le funding
- Temps pour que les ordres soient fill
- Pas trop tôt (risque de prix)

### Fermeture : X:01
- 1 minute après le funding
- Assez de temps pour confirmer le paiement
- Pas trop tard (risque de prix)

### Skip : 00:00, 08:00, 16:00 UTC
- Cycles Hyperliquid
- On ne snipe PAS ces heures
- Sinon on paie le funding HL (8h)

---

## 📅 **Planning 24h :**

```
00:00 ❌ SKIP (cycle HL)
01:00 ✅ SNIPE (00:58 → 01:01)
02:00 ✅ SNIPE (01:58 → 02:01)
03:00 ✅ SNIPE (02:58 → 03:01)
04:00 ✅ SNIPE (03:58 → 04:01)
05:00 ✅ SNIPE (04:58 → 05:01)
06:00 ✅ SNIPE (05:58 → 06:01)
07:00 ✅ SNIPE (06:58 → 07:01)
08:00 ❌ SKIP (cycle HL)
09:00 ✅ SNIPE (08:58 → 09:01)
10:00 ✅ SNIPE (09:58 → 10:01)
11:00 ✅ SNIPE (10:58 → 11:01)
12:00 ✅ SNIPE (11:58 → 12:01)
13:00 ✅ SNIPE (12:58 → 13:01)
14:00 ✅ SNIPE (13:58 → 14:01)
15:00 ✅ SNIPE (14:58 → 15:01)
16:00 ❌ SKIP (cycle HL)
17:00 ✅ SNIPE (16:58 → 17:01)
18:00 ✅ SNIPE (17:58 → 18:01)
19:00 ✅ SNIPE (18:58 → 19:01)
20:00 ✅ SNIPE (19:58 → 20:01)
21:00 ✅ SNIPE (20:58 → 21:01)
22:00 ✅ SNIPE (21:58 → 22:01)
23:00 ✅ SNIPE (22:58 → 23:01)

Total : 21 SNIPES par 24h
```

---

## 💰 **Calcul de profit :**

**Avec RESOLV (-0.1103%) :**
- 21 snipers × $11.03 = **$231.63 par jour**
- **Sur $10,000 = 2.31% par jour**
- **Sur 1 mois = ~70%** (si rate constant)

**Avec IP (-0.0713%) :**
- 21 snipers × $7.13 = **$149.73 par jour**
- **Sur $10,000 = 1.50% par jour**
- **Sur 1 mois = ~45%**

---

## ⚠️ **Risques :**

1. **Frais de gas :**
   - 21 × 2 ouvertures + 21 × 2 fermetures = **84 transactions/jour**
   - Extended (Starknet) : ~$0.02-0.05 par tx
   - Hyperliquid : ~$0.001-0.01 par tx
   - Total : ~$2-5 par jour sur $10k → **OK**

2. **Slippage :**
   - Sur des ordres market, le prix peut bouger
   - **Solution** : Utiliser des ordres LIMIT

3. **Risque de non-fill :**
   - Si ordre LIMIT pas fill avant X:00
   - On rate le funding
   - **Solution** : Prix LIMIT proche du market

4. **Delta non-neutral :**
   - Si sizes différentes entre LONG et SHORT
   - **Solution** : Vérifier après chaque ouverture

5. **Funding rate qui change :**
   - Le rate peut devenir négatif (on paie au lieu de recevoir)
   - **Solution** : Vérifier le rate avant chaque snipe

---

## 🚀 **Lancer le bot :**

```bash
py bot_sniper.py
```

**Choix :**
- 1 = DRY-RUN (simulation)
- 2 = LIVE (vraies positions)

---

## 📈 **Prochaines optimisations :**

1. **Multi-symboles :**
   - Sniper les 3-5 meilleurs symboles à chaque heure
   - Diversification

2. **Ordres LIMIT intelligents :**
   - Placer à mid-price + spread/2
   - Garantir le fill

3. **Vérification auto des sizes :**
   - Après ouverture, checker que LONG size = SHORT size
   - Si différent, ajuster ou fermer

4. **Monitoring des rates :**
   - Vérifier à X:57 si le rate est toujours positif
   - Si négatif, skip ce snipe

---

## 🎯 **C'est une RÉVOLUTION !**

Au lieu de **hold 21h par jour** avec risque de prix, on fait **63 minutes de risque total**.

**Ratio risque/reward :** 20x meilleur ! 🚀🚀🚀
