# 📚 GUIDE: Comment fonctionne l'arbitrage de funding

## 🎯 Principe de base

Le **funding rate** est un paiement périodique entre les traders :
- **Funding NÉGATIF** (ex: -0.50%) = Les **LONGS reçoivent**, les **SHORTS paient**
- **Funding POSITIF** (ex: +0.50%) = Les **SHORTS reçoivent**, les **LONGS paient**

---

## 💡 Exemple Concret: RESOLV

### Situation actuelle:
- **Extended:** Funding = -0.9155% (par heure)
- **Hyperliquid:** Funding = -0.6579% (par heure)

### Analyse:
Les deux sont **NÉGATIFS** → Les longs reçoivent de l'argent sur les deux exchanges.

**Mais Extended est plus négatif** → Tu reçois PLUS sur Extended que sur Hyperliquid !

---

## 🚀 Stratégie d'arbitrage

### Positions:
1. **LONG sur Extended** (taille: $10,000)
   - Tu **REÇOIS** 0.9155% par heure = **$91.55/h**
   
2. **SHORT sur Hyperliquid** (taille: $10,000)
   - Tu **PAIES** 0.6579% par heure = **$65.79/h**

### Résultat:
**Profit net = $91.55 - $65.79 = $25.76 par heure**

**Pas de risque de prix** car tu es long ET short (delta-neutral).

---

## 📊 Autre exemple: IP

### Situation:
- **Extended:** -0.4468%
- **Hyperliquid:** -0.1363%

### Stratégie:
1. **LONG Extended** → Reçois 0.4468%/h = $44.68/h
2. **SHORT Hyperliquid** → Paies 0.1363%/h = $13.63/h

**Profit = $44.68 - $13.63 = $31.05/h**

---

## 🔄 Monitoring en temps réel

Le bot **vérifie toutes les 60 secondes** si le spread est toujours profitable.

### Conditions de fermeture automatique:

**Scenario 1:** Le spread diminue
- Extended passe de -0.9155% à -0.6600%
- Hyperliquid reste à -0.6579%
- **Nouveau spread:** 0.0021% (2.1 bps) < Seuil (20 bps)
- → **FERMETURE AUTO** ✅

**Scenario 2:** Les funding changent de signe
- Extended passe de -0.9155% à +0.1000% (devient POSITIF)
- Maintenant tu **PAIES** sur Extended au lieu de recevoir
- → **FERMETURE AUTO** ✅

---

## 🎮 Commandes du bot

### Démarrer en mode DRY-RUN (simulation):
```bash
py main_extended_hyperliquid.py
# Choix: 1
```

### Démarrer en mode LIVE (vraies positions):
```bash
py main_extended_hyperliquid.py
# Choix: 2
# Confirmation: yes
```

---

## ⚙️ Configuration

### Seuils (dans le code):
```python
self.min_spread_bps = 5.0      # 5 bps = 0.05% minimum pour ouvrir
self.close_spread_bps = 2.0    # 2 bps = 0.02% pour fermer
self.check_interval = 60       # Vérifier toutes les 60 secondes
```

### Wallet:
Éditer `config/config.json` :
```json
{
  "wallet": {
    "address": "0xVOTRE_ADRESSE",
    "private_key": "VOTRE_CLE_PRIVEE"
  }
}
```

---

## ⚠️ Risques

1. **Frais de transaction:** Chaque ouverture/fermeture coûte des gas fees
2. **Slippage:** Sur les petits marchés, le prix peut bouger
3. **Liquidité:** Si le marché est illiquide, difficile de fermer
4. **Délai de funding:** Extended = 1h, mais les rates peuvent changer avant le paiement

---

## 📈 Résumé

**Le bot fait:**
1. Compare les funding rates Extended vs Hyperliquid
2. Trouve le meilleur spread (différence entre les deux)
3. Ouvre LONG sur l'exchange avec le rate le plus négatif (tu reçois plus)
4. Ouvre SHORT sur l'autre exchange (tu paies moins)
5. Monitor en temps réel
6. Ferme automatiquement quand le spread disparaît

**Tu gagnes la différence entre ce que tu reçois et ce que tu paies !**
