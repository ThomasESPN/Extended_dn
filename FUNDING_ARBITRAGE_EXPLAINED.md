# 🎯 Funding Arbitrage - La Vraie Stratégie

## Qu'est-ce que le Funding Arbitrage ?

Le **funding arbitrage** consiste à :
1. **Ouvrir une position LONG** sur un exchange qui **paie le funding** (Extended)
2. **Ouvrir une position SHORT** sur un autre exchange pour **neutraliser le risque de prix**
3. **Gagner le funding rate** sans exposition au prix

## ❌ Erreur Commune : Spreads Différents

### Ce qu'on faisait AVANT (MAUVAIS) :
```
Extended LONG  @ $96,815  (mid - 0.005%)
Hyperliquid SHORT @ $96,892  (mid + 0.005%)
Différence: $77 soit 0.08% 🚨
```

**Problème** : Tu n'es PAS delta-neutral !
- Si BTC monte à $97,000 :
  - Extended: +$185 (97000 - 96815)
  - Hyperliquid: -$108 (97000 - 96892)
  - **Net: +$77** = Tu as un biais LONG !

- Si BTC descend à $96,500 :
  - Extended: -$315
  - Hyperliquid: +$392
  - **Net: +$77** = Tu as toujours un biais LONG !

### Ce qu'on fait MAINTENANT (BON) :
```
Global Mid = $96,855 (moyenne des deux exchanges)

Extended LONG  @ $96,850  (global mid - 0.005%)
Hyperliquid SHORT @ $96,860  (global mid + 0.005%)
Différence: $10 soit 0.01% ✅
```

**Avantage** : Vraiment delta-neutral !
- Si BTC monte/descend, les P&L se compensent presque parfaitement
- Tu gagnes **uniquement le funding** Extended

---

## 💰 Calcul de Profitabilité

### Revenus : Funding Extended
Extended paie typiquement un funding **positif** pour les LONG :
- Funding rate: +0.01% toutes les 8h
- Par jour: +0.03%
- Par mois: ~+0.9%

Sur une position de $100 :
- Jour 1: +$0.03
- Mois 1: +$0.90
- An 1: +$10.95 (10.95% APY)

### Coûts : Fees

#### Maker Fees (post-only orders) :
- Extended MAKER: -0.02% (rebate = tu ES PAYÉ!)
- Hyperliquid MAKER: +0.02% (rebate aussi!)
- **Net: 0% ou légèrement positif** ✅

#### Ouverture + Fermeture (MAKER uniquement) :
- Ouverture: ~+0.04% (rebates)
- Fermeture: ~+0.04% (rebates)
- **Total: +0.08%** (tu ES PAYÉ pour ouvrir/fermer!)

### Profit Net

Sur 1 mois avec une position de $100 :
```
Funding Extended:  +$0.90
Maker Rebates:     +$0.08
-------------------------
Profit Net:        +$0.98

ROI mensuel: 0.98%
ROI annuel (composé): ~12.4% APY
```

🎉 **Profit sans risque directionnel !**

---

## 🔧 Implémentation : Même Prix Global

### Ancienne Logique (MAUVAISE) :
```python
# Chaque exchange utilise son propre mid
extended_mid = (extended_bid + extended_ask) / 2
hyperliquid_mid = (hyperliquid_bid + hyperliquid_ask) / 2

extended_price = extended_mid - 0.005%    # $96,815
hyperliquid_price = hyperliquid_mid + 0.005%  # $96,892
# Différence: $77 🚨
```

### Nouvelle Logique (BONNE) :
```python
# Calculer UN SEUL mid price global
extended_mid = (extended_bid + extended_ask) / 2    # $96,819
hyperliquid_mid = (hyperliquid_bid + hyperliquid_ask) / 2  # $96,887
global_mid = (extended_mid + hyperliquid_mid) / 2   # $96,853

# Utiliser le MÊME mid pour les deux
extended_price = global_mid - 0.005%    # $96,848
hyperliquid_price = global_mid + 0.005%  # $96,858
# Différence: $10 ✅ (seulement 0.01%)
```

---

## 📊 Monitoring des Fills

### Problème avec les Ordres "Resting"

Quand un ordre est "resting" (en attente dans le carnet), il peut :
1. Être **fill** rapidement (si le prix bouge vers toi)
2. Rester en attente **longtemps** (si le prix ne bouge pas)
3. Ne **jamais fill** (si le prix s'éloigne)

### Solution : Vérifier les Positions, pas les Ordres

#### ❌ Ancienne méthode (vérifier le statut de l'ordre) :
```python
if order_status == 'resting':
    print("Ordre toujours en attente")
```
**Problème** : L'ordre peut être fill mais le statut pas à jour !

#### ✅ Nouvelle méthode (vérifier les positions) :
```python
positions = api.get_open_positions()
for pos in positions:
    if pos['symbol'] == 'ETH' and pos['size'] > 0:
        print("Ordre filled! Position détectée")
```
**Avantage** : Source de vérité = les positions réelles

---

## 🚀 Utilisation du WebSocket (À venir)

Pour détecter les fills **instantanément** au lieu de poll toutes les 5s :

### Hyperliquid WebSocket :
```python
# Subscribe au user events
ws.subscribe({
    "method": "subscribe",
    "subscription": {"type": "userEvents", "user": wallet_address}
})

# Recevoir les fills en temps réel
def on_message(msg):
    if msg['channel'] == 'user' and 'fill' in msg['data']:
        fill = msg['data']['fill']
        logger.success(f"✅ Fill détecté! {fill['coin']} @ ${fill['px']}")
```

### Extended WebSocket :
```python
# À implémenter selon leur documentation
# Probablement similaire avec un canal "trades" ou "fills"
```

**Avantages** :
- ✅ Détection **instantanée** (< 100ms)
- ✅ Pas de polling (économie de requêtes API)
- ✅ Permet de hedge immédiatement si asymétrique

---

## ⚠️ Risques et Mitigations

### 1. Risque de Slippage Asymétrique
**Problème** : Un ordre fill en MAKER, l'autre en TAKER
- Extended LONG @ $96,848 (MAKER)
- Hyperliquid SHORT @ $96,900 (TAKER car MAKER rejeté)
- Slippage: $52 soit 0.05%

**Mitigation** : 
- Retry avec offsets croissants
- Max 4 tentatives avant fallback MARKET
- Accepter 0.05% de slippage comme "coût d'assurance"

### 2. Risque de Funding Négatif
**Problème** : Le funding Extended devient négatif
- Tu dois PAYER pour ta position LONG
- Pas de profit, voire perte

**Mitigation** :
- Vérifier le funding rate **avant** d'ouvrir
- Fermer si funding devient < 0.005% par jour
- Configurer un seuil minimum dans le bot

### 3. Risque de Liquidation
**Problème** : Un exchange te liquide si volatilité extrême
- Hyperliquid: levier 20x = liquidation si -5%
- Extended: levier 10x = liquidation si -10%

**Mitigation** :
- Utiliser des leviers **modérés** (5x max)
- Garder de la marge disponible (50% buffer)
- Stop loss automatique si une position atteint -3%

---

## 📝 Checklist Avant de Lancer le Bot

- [ ] Vérifier que le funding Extended est **positif** (> 0.01% par jour)
- [ ] Vérifier que les spreads sont **raisonnables** (< 0.1%)
- [ ] Calculer le **global mid** (moyenne des deux exchanges)
- [ ] Placer les ordres MAKER avec le **même prix mid**
- [ ] Vérifier les **positions réelles** (pas juste les ordres)
- [ ] Calculer la **différence de prix** entre les fills
- [ ] Confirmer que la différence est **< 0.1%** pour du vrai delta-neutral
- [ ] Monitorer le **funding rate** toutes les heures

---

## 🎯 Configuration Recommandée

### Pour le Bot Automatique :
```json
{
  "funding_arbitrage": {
    "min_funding_rate_daily": 0.01,  // 0.01% par jour minimum
    "max_price_diff_percent": 0.1,   // 0.1% max entre les fills
    "position_size_usd": 100,         // Taille de position
    "leverage_extended": 5,           // Levier modéré
    "leverage_hyperliquid": 5,
    "check_funding_interval": 3600,   // Vérifier funding toutes les 1h
    "rebalance_threshold": 0.5        // Rebalancer si diff > 0.5%
  }
}
```

### Offsets pour MAKER :
```python
# Offsets progressifs pour retry
MAKER_OFFSETS = [0.005, 0.02, 0.05, 0.1]  # 0.005% → 0.1%

# Maximum acceptable pour delta-neutral
MAX_PRICE_DIFF_PCT = 0.1  # 0.1% entre extended et hyperliquid
```

---

## 📈 ROI Attendu

| Scénario | Funding Extended | Fees Maker | Slippage | ROI Mensuel | ROI Annuel |
|----------|-----------------|------------|----------|-------------|------------|
| **Optimal** | +0.03%/jour | +0.04% | 0% | +0.98% | ~12.4% |
| **Bon** | +0.02%/jour | +0.02% | -0.02% | +0.60% | ~7.4% |
| **Acceptable** | +0.01%/jour | 0% | -0.05% | +0.25% | ~3.0% |
| **Mauvais** | +0.005%/jour | -0.02% | -0.1% | -0.05% | -0.6% ❌ |

**Conclusion** : Rentable si funding > 0.01%/jour et slippage < 0.05%

---

## 🔄 Cycle Complet

1. **Check Funding** : Vérifier que funding Extended > 0.01%/jour
2. **Calculate Mid** : global_mid = (extended_mid + hyperliquid_mid) / 2
3. **Place MAKER** : Extended LONG et Hyperliquid SHORT au même mid (±0.005%)
4. **Monitor Fills** : Vérifier les positions réelles (WebSocket ou polling)
5. **Verify Delta-Neutral** : Confirmer que price_diff < 0.1%
6. **Hold Position** : Garder ouvert pour collecter le funding
7. **Check Daily** : Vérifier funding rate tous les jours
8. **Close if Negative** : Fermer si funding devient < 0.005%/jour
9. **Collect Profit** : Funding payé toutes les 8h automatiquement

**Durée optimale** : 1-4 semaines (équilibre entre funding collecté et risque de retournement)

---

**Status** : ✅ **Stratégie Optimisée** - Prix global mid + vérification positions
