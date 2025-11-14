// wallet-agent.js — version SDK, index perp auto

import { ethers } from "https://cdn.jsdelivr.net/npm/ethers@6.11.1/dist/ethers.min.js";
import * as hl from "https://esm.sh/jsr/@nktkas/hyperliquid";

// ==================== CONFIG ====================
const IS_MAINNET = true;

const URLS = {
  true: "https://api.hyperliquid.xyz",
  false: "https://api.hyperliquid-testnet.xyz",
};

// Configuration Supabase
const SUPABASE_CONFIG = {
  url: "https://rfvrhtvpthxurqvibdyz.supabase.co",
  anonKey: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJmdnJodHZwdGh4dXJxdmliZHl6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTc4ODE2NDEsImV4cCI6MjA3MzQ1NzY0MX0.dTjOE6Rly9lEmaCdl0_DyR4KiiG0wA1Xb5YHmQ041N8"
};

// Initialiser Supabase
const supabase = window.supabase.createClient(SUPABASE_CONFIG.url, SUPABASE_CONFIG.anonKey);

let agentWallet = null;   // clé agent (ethers.Wallet)
let mainAddress = null;   // EOA (MetaMask)

// Variables pour le grid trading
let ws = null;
let isBotRunning = false;
let currentTokenMeta = null;
let lastBidPrice = null;
let lastAskPrice = null;
let activeOrders = new Map();
let orderCounter = 0;

// Variables pour la reconnexion automatique
let wsReconnectAttempts = 0;
let maxWsReconnectAttempts = 10;
let wsReconnectInterval = null;
let walletWsReconnectAttempts = 0;
let maxWalletWsReconnectAttempts = 10;
let walletWsReconnectInterval = null;

// Variables pour le mode Humanizer
let humanizerMode = false;
let maxVariation = 0;
let holdingDurationMin = 0;
let holdingDurationMax = 0;
let entryPrice = null;
let entryTime = null;
let sellScheduled = false;
let sellTimeout = null;

// Système de cycles indépendants
let cycleTable = []; // Tableau des cycles avec budget individuel
let activeCycles = new Map(); // Cycles actuellement en cours (achat fait, vente programmée)
let totalCycles = 0; // Nombre total de cycles créés
let cycleCounter = 0; // Compteur global des cycles (infini)
let currentCycle = 0;
let cyclesData = new Map(); // stocke les données de chaque cycle
let nextBuyTimeout = null;
let isWaitingForNextCycle = false;

// Timer variables
let botStartTime = null;
let botDuration = null; // in minutes
let timerInterval = null;

// Wallet info WebSocket variables
let walletWs = null;
let isWalletConnected = false;

// No automatic restoration - user must connect manually each time
// This ensures security and prevents automatic reconnection

// Initialize wallet info display on page load
window.addEventListener("DOMContentLoaded", () => {
  // Clear any stored data on page load for security
  localStorage.removeItem("agentPrivKey");
  localStorage.removeItem("agentAddress");
  localStorage.removeItem("mainAddress");
  
  // Reset global variables
  agentWallet = null;
  mainAddress = null;
  isWalletConnected = false;
  
  // Update wallet info display after a short delay to ensure DOM is ready
  setTimeout(() => {
    updateWalletInfoDisplay();
  }, 100);
});

// ==================== HELPERS ====================
function getTransport() {
  return new hl.HttpTransport(IS_MAINNET ? URLS.true : URLS.false);
}

/**
 * Configuration des protocoles avec leurs builder addresses et fees
 */
const PROTOCOL_CONFIG = {
  based: {
    builderAddress: "0x1924b8561eeF20e70Ede628A296175D358BE80e5",
    feePercentage: "0.1%", // 0.1% pour Based
    feeValue: 100 // 100 en dixièmes de bps pour 0.1%
  },
  unit: {
    builderAddress: "0xbe698e3d926a5cc2658aa6cffcc7bb0857314c82", // Adresse Unit mise à jour
    feePercentage: "0.04%", // 0.04% pour Unit
    feeValue: 40 // 40 en dixièmes de bps pour 0.04%
  }
};

/**
 * Approuve le builder fee pour un protocole donné
 * Utilise la même méthode que lors de la connexion (approveAgent)
 */
async function approveBuilderFee(protocol) {
  try {
    if (!mainAddress) {
      throw new Error("Main wallet not found. Please connect your wallet first.");
    }

    const config = PROTOCOL_CONFIG[protocol];
    if (!config) {
      throw new Error(`Unknown protocol: ${protocol}`);
    }

    log(`🔐 Requesting manual approval for ${protocol.toUpperCase()} protocol...`);
    log(`📋 Builder address: ${config.builderAddress}`);
    log(`💰 Fee percentage: ${config.feePercentage}`);

    // Vérifier que MetaMask est disponible
    if (typeof window.ethereum === "undefined") {
      throw new Error("MetaMask not detected. Please install MetaMask to approve builder fees.");
    }

    const provider = new ethers.BrowserProvider(window.ethereum);
    const signer = await provider.getSigner();

    // Utiliser la même approche que lors de la connexion avec le SDK Hyperliquid
    const exchangeViaEOA = new hl.ExchangeClient({
      wallet: signer,
      transport: getTransport(),
    });

    log(`📝 Requesting signature for builder fee approval...`);
    log(`📋 Builder address: ${config.builderAddress}`);

    // Utiliser la méthode du SDK pour approuver le builder fee
    // Cette méthode demande automatiquement la signature à l'utilisateur
    const approveResult = await exchangeViaEOA.approveBuilderFee({
      builder: config.builderAddress,
      maxFeeRate: config.feePercentage
    });

    log(`✍️ Transaction signed successfully`);
    log(`📄 Approval result: ${JSON.stringify(approveResult)}`);

    if (approveResult?.status === "ok") {
      log(`✅ Builder fee approved successfully for ${protocol.toUpperCase()}`);
      log(`📄 Transaction result: ${JSON.stringify(approveResult)}`);
      return approveResult;
    } else {
      log(`❌ Builder fee approval failed: ${JSON.stringify(approveResult)}`);
      throw new Error(`Builder fee approval failed: ${JSON.stringify(approveResult)}`);
    }

  } catch (error) {
    log(`❌ Error approving builder fee for ${protocol}: ${error.message}`);
    throw error;
  }
}

/**
 * Met à jour le protocole et approuve le builder fee correspondant
 */
async function updateProtocol(newProtocol) {
  try {
    log(`🔄 Switching to ${newProtocol.toUpperCase()} protocol...`);
    
    // Approuver le builder fee pour le nouveau protocole
    await approveBuilderFee(newProtocol);
    
    // Mettre à jour la configuration globale
    window.currentProtocol = newProtocol;
    
    // Filtrer les tokens selon le protocole
    await filterTokensByProtocol(newProtocol);
    
    log(`✅ Successfully switched to ${newProtocol.toUpperCase()} protocol`);
    
  } catch (error) {
    log(`❌ Failed to switch to ${newProtocol.toUpperCase()} protocol: ${error.message}`);
    throw error;
  }
}

/**
 * Filtre les tokens disponibles selon le protocole choisi
 */
async function filterTokensByProtocol(protocol) {
  try {
    const select = document.getElementById("token-select");
    const allOptions = Array.from(select.options);
    
    // Cacher/montrer les tokens selon le protocole
    allOptions.forEach(option => {
      if (option.value) { // Ignorer l'option vide
        const tokenMeta = JSON.parse(option.dataset.meta);
        const tokenName = tokenMeta.name;
        
        if (protocol === "unit") {
          // Pour Unit, afficher uniquement UBTC, UETH et USOL
          if (tokenName === "UBTC" || tokenName === "UETH" || tokenName === "USOL") {
            option.style.display = "block";
            option.disabled = false;
          } else {
            option.style.display = "none";
            option.disabled = true;
          }
        } else {
          // Pour Based, montrer tous les tokens
          option.style.display = "block";
          option.disabled = false;
        }
      }
    });
    
    // Sélectionner le premier token disponible
    const firstAvailableOption = allOptions.find(option => 
      option.value && !option.disabled && option.style.display !== "none"
    );
    
    if (firstAvailableOption) {
      select.value = firstAvailableOption.value;
      log(`🎯 Auto-selected token: ${firstAvailableOption.textContent}`);
    }
    
  } catch (error) {
    log(`❌ Error filtering tokens by protocol: ${error.message}`);
  }
}

/**
 * Vérifie si une adresse est dans la whitelist Supabase
 */
async function checkWhitelist(address) {
  try {
    log(`🔍 Checking whitelist for address: ${address}`);
    
    const { data, error } = await supabase
      .from('whitelist')
      .select('*')
      .eq('wallet_adress', address.toLowerCase())
      .single();
    
    if (error) {
      if (error.code === 'PGRST116') {
        // Aucun résultat trouvé - adresse pas dans la whitelist
        log(`❌ Address ${address} not found in whitelist`);
        return false;
      }
      throw error;
    }
    
    if (data) {
      log(`✅ Address ${address} found in whitelist`);
      return true;
    }
    
    return false;
  } catch (error) {
    log(`❌ Error checking whitelist: ${error.message}`);
    throw new Error(`Whitelist verification error: ${error.message}`);
  }
}

/**
 * Custom popup functions
 */
function showPopup(type, title, content, showCancel = false) {
  const overlay = document.getElementById('popup-overlay');
  const icon = document.getElementById('popup-icon');
  const iconText = document.getElementById('popup-icon-text');
  const titleEl = document.getElementById('popup-title');
  const contentEl = document.getElementById('popup-content');
  const secondaryBtn = document.getElementById('popup-btn-secondary');
  
  // Set icon and type
  icon.className = `popup-icon ${type}`;
  if (type === 'success') {
    iconText.textContent = '✅';
  } else if (type === 'error') {
    iconText.textContent = '❌';
  } else {
    iconText.textContent = 'ℹ️';
  }
  
  // Set content
  titleEl.textContent = title;
  contentEl.innerHTML = content;
  
  // Show/hide cancel button
  secondaryBtn.style.display = showCancel ? 'block' : 'none';
  
  // Show popup
  overlay.classList.add('show');
  
  // Close on overlay click
  overlay.onclick = (e) => {
    if (e.target === overlay) {
      closePopup();
    }
  };
}

function closePopup() {
  const overlay = document.getElementById('popup-overlay');
  overlay.classList.remove('show');
}

// Make popup functions globally available
window.closePopup = closePopup;
window.showPopup = showPopup;

// Auto-disconnect when user leaves the page - MODIFIED to keep bot running
window.addEventListener('beforeunload', () => {
  window.isPageUnloading = true;
  // Le bot continue de fonctionner en arrière-plan
});

// Handle page visibility change - MODIFIED to keep bot running
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    // User switched tabs or minimized - keep bot running
  } else {
    // User returned to tab - no logging needed
  }
});

/**
 * Fonction de log pour afficher les messages dans l'interface
 */
function log(msg) {
  const logBox = document.getElementById("log");
  if (logBox) {
    logBox.value += "\n" + msg;
    logBox.scrollTop = logBox.scrollHeight;
  }
  console.log(msg); // Aussi dans la console pour debug
}


/**
 * Obtient les paramètres Humanizer depuis l'interface utilisateur
 */
function getHumanizerSettings() {
  const humanizerCheckbox = document.getElementById("humanizer-mode");
  const maxVariationInput = document.getElementById("max-variation");
  const holdingDurationMinInput = document.getElementById("holding-duration-min");
  const holdingDurationMaxInput = document.getElementById("holding-duration-max");
  
  return {
    enabled: humanizerCheckbox ? humanizerCheckbox.checked : false,
    maxVariation: maxVariationInput ? parseFloat(maxVariationInput.value) || 0 : 0,
    holdingDurationMin: holdingDurationMinInput ? parseInt(holdingDurationMinInput.value) || 0 : 0,
    holdingDurationMax: holdingDurationMaxInput ? parseInt(holdingDurationMaxInput.value) || 0 : 0
  };
}

/**
 * Calcule le nombre de cycles possibles basé sur le solde USDC
 */
function calculateMaxCycles(usdcBalance, sizePerTrade) {
  if (!usdcBalance || !sizePerTrade || sizePerTrade <= 0) {
    return 0;
  }
  
  // Calculer le nombre maximum de cycles possibles
  const maxCycles = Math.floor(usdcBalance / sizePerTrade);
  
  // Limiter à un maximum raisonnable pour éviter trop de cycles
  return Math.min(maxCycles, 10);
}

/**
 * Obtient le solde USDC actuel depuis l'interface
 */
function getCurrentUSDCBalance() {
  const balanceElement = document.getElementById("usdc-balance");
  if (balanceElement) {
    const balanceText = balanceElement.textContent;
    const match = balanceText.match(/(\d+\.?\d*)\s*USDC/);
    if (match) {
      return parseFloat(match[1]);
    }
  }
  return 0;
}

/**
 * Récupère les balances de tous les tokens de l'utilisateur via WebSocket
 */
async function getUserTokenBalances() {
  return new Promise((resolve) => {
    try {
      if (!mainAddress) {
        resolve([]);
        return;
      }

      const wsUrl = IS_MAINNET ? "wss://api.hyperliquid.xyz/ws" : "wss://api.hyperliquid-testnet.xyz/ws";
      const tempWs = new WebSocket(wsUrl);
      
      const timeout = setTimeout(() => {
        tempWs.close();
        resolve([]);
      }, 5000);

      tempWs.onopen = () => {
        const subscribeMsg = {
          method: "subscribe",
          subscription: {
            type: "webData2",
            user: mainAddress
          }
        };
        tempWs.send(JSON.stringify(subscribeMsg));
      };

      tempWs.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (data.channel === "webData2" && data.data) {
            const spotState = data.data.spotState || {};
            const balances = spotState.balances || [];
            
            const nonZeroBalances = balances.filter(balance => {
              const total = parseFloat(balance.total) || 0;
              return total > 0 && balance.coin !== "USDC";
            });

            clearTimeout(timeout);
            tempWs.close();
            resolve(nonZeroBalances);
          }
        } catch (error) {
          log(`❌ Error parsing wallet data: ${error.message}`);
        }
      };

      tempWs.onerror = () => {
        clearTimeout(timeout);
        tempWs.close();
        resolve([]);
      };

    } catch (error) {
      log(`❌ Error getting user token balances: ${error.message}`);
      resolve([]);
    }
  });
}

/**
 * Vend le token sur lequel le bot tournait en USDC
 */
async function sellCurrentTokenToUSDC() {
  try {
    if (!currentTokenMeta) {
      log("⚠️ No current token to sell - bot was not running on any specific token");
      return;
    }

    log(`🔄 Starting automatic sell of ${currentTokenMeta.name} to USDC...`);
    
    // Get user's balance for the current token using a simpler approach
    let tokenAmount = 0;
    try {
      const tokenBalances = await getUserTokenBalances();
      const currentTokenBalance = tokenBalances.find(balance => balance.coin === currentTokenMeta.name);
      
      if (!currentTokenBalance) {
        log(`✅ No ${currentTokenMeta.name} to sell - already in USDC`);
        return;
      }

      tokenAmount = parseFloat(currentTokenBalance.total);
      if (tokenAmount <= 0) {
        log(`✅ No ${currentTokenMeta.name} to sell - balance is zero`);
        return;
      }
    } catch (error) {
      log(`⚠️ Could not get token balance via API, trying alternative method: ${error.message}`);
      // For now, we'll assume there's a balance and let the order fail if there isn't
      tokenAmount = 1; // Placeholder - the order will fail if no balance
    }

    log(`📊 Found ${tokenAmount} ${currentTokenMeta.name} to sell`);

    // Restore agent if needed
    const privKey = localStorage.getItem("agentPrivKey");
    const agentAddress = localStorage.getItem("agentAddress");
    if (!privKey || !agentAddress) {
      throw new Error("No agent found");
    }
    
    const agentWallet = new ethers.Wallet(privKey);
    
    // Client via agent
    const exchangeViaAgent = new hl.ExchangeClient({
      wallet: agentWallet.privateKey,
      transport: getTransport(),
    });

    // Get current bid price for selling
    const wsUrl = IS_MAINNET ? "wss://api.hyperliquid.xyz/ws" : "wss://api.hyperliquid-testnet.xyz/ws";
    const tokenId = `@${currentTokenMeta.token_id}`;
    
    // Create a temporary WebSocket to get current price
    const tempWs = new WebSocket(wsUrl);
    
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        tempWs.close();
        reject(new Error("Price fetch timeout"));
      }, 5000);

      tempWs.onopen = () => {
        const subscribeMsg = {
          method: "subscribe",
          subscription: {
            type: "l2Book",
            coin: tokenId
          }
        };
        tempWs.send(JSON.stringify(subscribeMsg));
      };

      tempWs.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.data && data.data.levels && data.data.levels.length >= 2) {
            const bids = data.data.levels[0];
            if (bids.length > 0) {
              const bidPrice = parseFloat(bids[0].px);
              clearTimeout(timeout);
              tempWs.close();
              
              // Create sell order
              const sellSize = tokenAmount.toFixed(currentTokenMeta.szDecimals);
              const order = {
                a: currentTokenMeta.market_index,
                b: false, // sell
                p: bidPrice.toString(),
                s: sellSize,
                r: false,
                t: { limit: { tif: "Ioc" } },
              };

              // Configuration du builder selon le protocole actuel
              const currentProtocol = window.currentProtocol || "based";
              const protocolConfig = PROTOCOL_CONFIG[currentProtocol];
              const builderParams = {
                b: protocolConfig.builderAddress,
                f: protocolConfig.feeValue
              };

              exchangeViaAgent.order({ 
                orders: [order], 
                grouping: "na",
                builder: builderParams
              }).then(resp => {
                if (resp?.status === "ok") {
                  log(`✅ Sold ${sellSize} ${currentTokenMeta.name} @ ${bidPrice.toFixed(6)} ($${(tokenAmount * bidPrice).toFixed(2)})`);
                } else {
                  log(`❌ Failed to sell ${currentTokenMeta.name}: ${JSON.stringify(resp)}`);
                }
                resolve();
              }).catch(error => {
                log(`❌ Error selling ${currentTokenMeta.name}: ${error.message}`);
                resolve();
              });
            }
          }
        } catch (error) {
          log(`❌ Error parsing price data for ${currentTokenMeta.name}: ${error.message}`);
          clearTimeout(timeout);
          tempWs.close();
          resolve();
        }
      };

      tempWs.onerror = () => {
        clearTimeout(timeout);
        tempWs.close();
        reject(new Error("WebSocket error"));
      };
    });

    log("✅ Automatic sell process completed");

  } catch (error) {
    log(`❌ Error in sellCurrentTokenToUSDC: ${error.message}`);
  }
}

async function loadTokens(path) {
  const resp = await fetch(path);
  if (!resp.ok) throw new Error("Impossible de charger le fichier tokens");
  return resp.json();
}

/**
 * Résout l'index PERP côté exchange à partir d’un symbole UI (ex: "UETH").
 * On essaie d’abord le symbole tel quel, puis sans le "U" initial (UETH -> ETH).
 */
async function resolvePerpIndex(symbol) {
  const info = new hl.InfoClient({ transport: getTransport() });
  const meta = await info.meta();
  const universe = meta.universe || meta.perpMeta?.universe || [];

  let idx = universe.findIndex(a => a.name?.toUpperCase() === symbol.toUpperCase());
  if (idx !== -1) return idx;

  if (symbol.toUpperCase().startsWith("U")) {
    const bare = symbol.slice(1);
    idx = universe.findIndex(a => a.name?.toUpperCase() === bare.toUpperCase());
    if (idx !== -1) return idx;
  }

  throw new Error(`Symbole ${symbol} introuvable dans les perps (univers=${universe.map(u=>u.name).join(", ")})`);
}

// ==================== INIT UI ====================
export async function initTokens(path = "./spot_tokens_detailed_mainnet.json") {
  const tokensMeta = await loadTokens(path);
  const select = document.getElementById("token-select");
  select.innerHTML = "";

  tokensMeta.tokens.forEach(token => {
    const opt = document.createElement("option");
    opt.value = token.market_index;          // laissé tel quel pour l'UI
    opt.textContent = token.name;            // ex: "UETH"
    opt.dataset.meta = JSON.stringify(token);
    select.appendChild(opt);
  });

  // Initialiser le protocole par défaut (Based)
  window.currentProtocol = "based";
  await filterTokensByProtocol("based");

  return tokensMeta;
}

// Exporter la fonction updateProtocol pour l'interface HTML
window.updateProtocol = updateProtocol;

// ==================== CREATE AGENT ====================
export async function createAgent() {
  if (typeof window.ethereum === "undefined") {
    throw new Error("MetaMask not detected");
  }

  const provider = new ethers.BrowserProvider(window.ethereum);
  const signer   = await provider.getSigner();
  mainAddress    = await signer.getAddress();

  // Vérification de la whitelist avant de continuer
  log("🔍 Checking access...");
  const isWhitelisted = await checkWhitelist(mainAddress);
  
  if (!isWhitelisted) {
    const errorTitle = "Access Denied";
    const errorContent = `
      <p>Your address <strong>${mainAddress}</strong> is not authorized to use this bot.</p>
      <p>To get access, please join our Discord server:</p>
      <p style="text-align: center; margin: 1rem 0;">
        <a href="https://discord.gg/cDXxWnt5GW" target="_blank" style="
          display: inline-block;
          background: #5865F2;
          color: white;
          padding: 0.8rem 1.5rem;
          border-radius: 8px;
          text-decoration: none;
          font-weight: 600;
          transition: all 0.3s ease;
        ">Join Discord Server</a>
      </p>
      <p>Once you join and your address is added to the whitelist, you will be able to use the bot.</p>
    `;
    
    log("❌ Access denied - Address not in whitelist");
    showPopup('error', errorTitle, errorContent);
    throw new Error("Address not authorized - Join Discord to get access");
  }

  if (agentWallet) {
    showPopup('info', 'Agent Already Exists', `Agent already exists: ${agentWallet.address}`);
    return agentWallet;
  }

  // Generate local agent key
  agentWallet = ethers.Wallet.createRandom();
  const agentAddress = agentWallet.address;

  // Authorize agent via EOA (SDK handles EIP-712)
  const exchangeViaEOA = new hl.ExchangeClient({
    wallet: signer,
    transport: getTransport(),
  });

  await exchangeViaEOA.approveAgent({ agentAddress });

  // Persistence
  localStorage.setItem("agentPrivKey", agentWallet.privateKey);
  localStorage.setItem("agentAddress", agentAddress);
  localStorage.setItem("mainAddress", mainAddress);

  showPopup('success', 'Agent Created Successfully', `New agent created: ${agentAddress}`);
  
  // Update wallet info display
  updateWalletInfoDisplay();
  
  return agentWallet;
}

// ==================== PLACE ORDER ====================
export async function placeOrder(_marketIndexFromUI, price, size, szDecimals) {
  if (!price || isNaN(parseFloat(price))) throw new Error("Invalid price");
  if (!size  || isNaN(parseFloat(size)))  throw new Error("Invalid size");
  if (szDecimals === undefined)           throw new Error("szDecimals missing for this token");

  // Get symbol from UI, then resolve PERP index on exchange side
  const select = document.getElementById("token-select");
  const tokenMeta = JSON.parse(select.selectedOptions[0].dataset.meta);

  // Normalize size/price
  const formattedSize = parseFloat(size).toFixed(szDecimals);
  const basePrice = parseFloat(price);

  // Use the new IOC order with fallback system
  const success = await placeIOCOrderWithFallback(tokenMeta, basePrice, formattedSize, true);
  
  if (!success) {
    throw new Error("❌ Order failed: All IOC fallback attempts failed");
  }

  showPopup('success', 'Order Placed Successfully', 'Your order has been placed successfully!');
  return { status: "ok" };
}

// ==================== GRID TRADING FUNCTIONS ====================

/**
 * Gets the token ID for WebSocket (format @X)
 */
function getTokenIdForWebSocket(tokenMeta) {
  return `@${tokenMeta.token_id}`;
}

/**
 * Connects to WebSocket and subscribes to token prices
 */
export function connectWebSocket(tokenMeta) {
  return new Promise((resolve, reject) => {
    try {
      const wsUrl = IS_MAINNET ? "wss://api.hyperliquid.xyz/ws" : "wss://api.hyperliquid-testnet.xyz/ws";
      const tokenId = getTokenIdForWebSocket(tokenMeta);
      
      log(`🔌 WebSocket connection for ${tokenMeta.name} (${tokenId})`);
      
      ws = new WebSocket(wsUrl);
      
      ws.onopen = () => {
        log("✅ WebSocket connected");
        
        // Wait a bit to ensure WebSocket is fully ready
        setTimeout(() => {
          if (ws && ws.readyState === WebSocket.OPEN) {
            // Subscribe to orderbook
            const subscribeMsg = {
              method: "subscribe",
              subscription: {
                type: "l2Book",
                coin: tokenId
              }
            };
            
            ws.send(JSON.stringify(subscribeMsg));
            log(`📡 Orderbook subscription: ${JSON.stringify(subscribeMsg)}`);
            resolve();
          } else {
            log("❌ WebSocket not ready for sending");
            reject(new Error("WebSocket not ready"));
          }
        }, 100);
      };
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (data.data && data.data.levels && data.data.levels.length >= 2) {
            const bids = data.data.levels[0];
            const asks = data.data.levels[1];
            
            if (bids.length > 0 && asks.length > 0) {
              lastBidPrice = parseFloat(bids[0].px);
              lastAskPrice = parseFloat(asks[0].px);
              
              updatePriceDisplay();
              
              // If bot is running, process prices
              if (isBotRunning) {
                processGridTrading();
              }
            }
          }
        } catch (error) {
          // Only log WebSocket errors if bot is still running
          if (isBotRunning) {
            log(`❌ WebSocket parsing error: ${error.message}`);
          }
        }
      };
      
      ws.onerror = (error) => {
        log(`❌ WebSocket error: ${error}`);
        reject(error);
      };
      
      ws.onclose = () => {
        log("🔌 WebSocket closed");
        if (isBotRunning) {
          log("⚠️ WebSocket closed during bot execution - attempting reconnection...");
          // Tenter de reconnecter automatiquement si le bot est en cours d'exécution
          attemptWebSocketReconnection();
        }
      };
      
    } catch (error) {
      reject(error);
    }
  });
}

/**
 * Attempts to reconnect the main WebSocket
 */
async function attemptWebSocketReconnection() {
  if (wsReconnectAttempts >= maxWsReconnectAttempts) {
    log(`❌ Maximum WebSocket reconnection attempts reached (${maxWsReconnectAttempts})`);
    return;
  }
  
  wsReconnectAttempts++;
  const delay = Math.min(1000 * Math.pow(2, wsReconnectAttempts - 1), 30000); // Exponential backoff, max 30s
  
  log(`🔄 Attempting WebSocket reconnection ${wsReconnectAttempts}/${maxWsReconnectAttempts} in ${delay/1000}s...`);
  
  wsReconnectInterval = setTimeout(async () => {
    try {
      if (isBotRunning && currentTokenMeta) {
        await connectWebSocket(currentTokenMeta);
        wsReconnectAttempts = 0; // Reset counter on successful reconnection
        log("✅ WebSocket reconnected successfully");
      }
    } catch (error) {
      log(`❌ WebSocket reconnection failed: ${error.message}`);
      if (isBotRunning) {
        attemptWebSocketReconnection(); // Try again
      }
    }
  }, delay);
}

/**
 * Updates price display
 */
function updatePriceDisplay() {
  const priceElement = document.getElementById("current-prices");
  if (priceElement && lastBidPrice && lastAskPrice) {
    const spread = lastAskPrice - lastBidPrice;
    const spreadPercent = ((spread / lastBidPrice) * 100).toFixed(4);
    priceElement.innerHTML = `
      <br>BID: ${lastBidPrice.toFixed(6)} | ASK: ${lastAskPrice.toFixed(6)}
      <br>Spread: ${spread.toFixed(6)} (${spreadPercent}%)
    `;
  }
}

/**
 * Processes grid trading logic
 */
async function processGridTrading() {
  // IMMEDIATELY check if bot is still running
  if (!isBotRunning) {
    return;
  }
  
  if (!lastBidPrice || !lastAskPrice || !currentTokenMeta) {
    return;
  }
  
  try {
    // Double check if bot is still running before processing
    if (!isBotRunning) {
      return;
    }
    
    // Get current humanizer settings
    const humanizerSettings = getHumanizerSettings();
    humanizerMode = humanizerSettings.enabled;
    maxVariation = humanizerSettings.maxVariation;
    holdingDurationMin = humanizerSettings.holdingDurationMin;
    holdingDurationMax = humanizerSettings.holdingDurationMax;
    
    if (humanizerMode) {
      await processHumanizerTrading();
    } else {
      // Check active orders and cancel if necessary
      await checkAndCancelOldOrders();
      
      // Place new orders according to grid strategy
      await placeGridOrders();
    }
    
  } catch (error) {
    if (isBotRunning) {
      log(`❌ Grid trading error: ${error.message}`);
    }
  }
}

/**
 * Processes humanizer trading logic
 */
async function processHumanizerTrading() {
  try {
    // IMMEDIATELY check if bot is still running
    if (!isBotRunning) {
      return;
    }
    
    // Si on n'a pas encore initialisé, démarrer le système
    if (totalCycles === 0) {
      await initializeIndependentCycles();
      return;
    }
    
    // Double check if bot is still running
    if (!isBotRunning) {
      return;
    }
    
    // Vérifier les conditions de vente pour tous les cycles actifs
    if (activeCycles.size > 0) {
      // Log moins fréquent pour éviter le spam
      if (Math.random() < 0.05) { // Log seulement 5% du temps
        log(`🔍 [Humanizer] Checking ${activeCycles.size} active cycles`);
      }
      await checkAllActiveCycles();
    }
    
    // Afficher le statut des cycles actifs
    if (Math.random() < 0.01) { // Log seulement 1% du temps pour éviter le spam
      log(`📊 [Humanizer] Statut: ${activeCycles.size} cycles actifs, #${cycleCounter} cycles totaux`);
    }
    
  } catch (error) {
    if (isBotRunning) {
      log(`❌ Humanizer trading error: ${error.message}`);
    }
  }
}

/**
 * Initialise le système de cycles indépendants
 */
async function initializeIndependentCycles() {
  // Éviter les initialisations multiples
  if (totalCycles > 0) {
    return;
  }
  
  const gridSize = parseFloat(document.getElementById("grid-size").value);
  const usdcBalance = getCurrentUSDCBalance();
  
  if (!gridSize || gridSize <= 0) {
    log("❌ Invalid size in $ per trade");
    return;
  }
  
  // Calculer le nombre de cycles avec division euclidienne
  totalCycles = Math.floor(usdcBalance / gridSize);
  
  if (totalCycles === 0) {
    log("❌ Insufficient USDC balance for trading");
    return;
  }
  
  log(`🤖 [Humanizer] Independent cycles system initialized`);
  log(`💰 Available USDC balance: ${usdcBalance.toFixed(2)} USDC`);
  log(`🔄 Number of cycles: ${totalCycles} ($${gridSize} per cycle)`);
  
  // Créer le tableau des cycles
  cycleTable = [];
  for (let i = 1; i <= totalCycles; i++) {
    const cycleData = {
      cycleNumber: i,
      budget: gridSize,
      remainingBudget: gridSize,
      status: 'waiting', // waiting, active, completed
      currentPosition: null, // null, 'buy', 'sell'
      entryPrice: null,
      entryTime: null,
      buyTimeout: null,
      sellTimeout: null
    };
    cycleTable.push(cycleData);
    
    // Lancer chaque cycle avec un délai aléatoire
    await startIndependentCycle(cycleData);
  }
  
  log(`📋 [Humanizer] Table of ${totalCycles} cycles created and launched`);
}

/**
 * Démarre un cycle indépendant
 */
async function startIndependentCycle(cycleData) {
  // Calculer un délai aléatoire pour l'achat
  let randomMinutes, randomDelay;
  
  if (holdingDurationMin === 0 && holdingDurationMax === 0) {
    // Si les deux valeurs sont 0, délai très court (1-5 secondes)
    randomMinutes = Math.random() * 4 + 1; // 1-5 secondes
    randomDelay = randomMinutes * 1000; // Convertir en millisecondes
    log(`🔄 [Humanizer] Cycle ${cycleData.cycleNumber} scheduled in ${randomMinutes.toFixed(1)} seconds (holding duration = 0)`);
  } else if (holdingDurationMin === holdingDurationMax) {
    // Si min = max, délai fixe
    randomMinutes = holdingDurationMin;
    randomDelay = randomMinutes * 60 * 1000;
    if (randomMinutes < 1) {
      const seconds = Math.round(randomMinutes * 60);
      log(`🔄 [Humanizer] Cycle ${cycleData.cycleNumber} scheduled in ${seconds} seconds (fixed delay)`);
    } else {
      log(`🔄 [Humanizer] Cycle ${cycleData.cycleNumber} scheduled in ${randomMinutes} minutes (fixed delay)`);
    }
  } else {
    // Délai aléatoire normal
    randomMinutes = Math.random() * (holdingDurationMax - holdingDurationMin) + holdingDurationMin;
    randomDelay = randomMinutes * 60 * 1000;
    if (randomMinutes < 1) {
      const seconds = Math.round(randomMinutes * 60);
      log(`🔄 [Humanizer] Cycle ${cycleData.cycleNumber} scheduled in ${seconds} seconds`);
    } else {
      log(`🔄 [Humanizer] Cycle ${cycleData.cycleNumber} scheduled in ${randomMinutes.toFixed(1)} minutes`);
    }
  }
  
  const currentTime = new Date();
  const launchTime = new Date(currentTime.getTime() + randomDelay);
  const launchTimeStr = launchTime.toLocaleTimeString('fr-FR', { hour12: false });
  
  log(`🔄 [Humanizer] Cycle ${cycleData.cycleNumber} - Launch at ${launchTimeStr}`);
  
  // Programmer l'achat
  const timeoutId = setTimeout(async () => {
    if (isBotRunning && cycleData.status === 'waiting') {
      // Double check if bot is still running before executing
      if (isBotRunning) {
        await executeIndependentCycleBuy(cycleData);
      }
    }
  }, randomDelay);
  
  cycleData.buyTimeout = timeoutId;
}

/**
 * Exécute un achat pour un cycle indépendant
 */
async function executeIndependentCycleBuy(cycleData) {
  try {
    // Vérifier le budget restant
    if (cycleData.remainingBudget <= 0) {
      log(`⚠️ [Humanizer] Cycle ${cycleData.cycleNumber} - Budget exhausted`);
      cycleData.status = 'completed';
      return;
    }
    
    // Vérifier la balance USDC disponible
    const currentBalance = getCurrentUSDCBalance();
    if (currentBalance < 10) {
      log(`⚠️ [Humanizer] Cycle ${cycleData.cycleNumber} - Balance insuffisante: ${currentBalance.toFixed(2)} USDC < 10 USDC minimum`);
      log(`🛑 [Humanizer] Stopping bot - Balance too low`);
      stopBot();
      return;
    }
    
    // Utiliser le montant disponible (budget du cycle ou balance, le plus petit)
    const availableAmount = Math.min(cycleData.remainingBudget, currentBalance);
    
    // Vérifier que le montant disponible est suffisant (minimum 10$)
    if (availableAmount < 10) {
      log(`⚠️ [Humanizer] Cycle ${cycleData.cycleNumber} - Montant disponible insuffisant: ${availableAmount.toFixed(2)} USDC < 10 USDC minimum`);
      log(`🛑 [Humanizer] Stopping bot - Amount per trade too low`);
      stopBot();
      return;
    }
    
    // Calculer la taille d'achat basée sur le montant disponible
    const buySize = (availableAmount / lastAskPrice).toFixed(currentTokenMeta.szDecimals);
    
    const currentTime = new Date();
    const timeStr = currentTime.toLocaleTimeString('fr-FR', { hour12: false });
    
    // Incrémenter le compteur global
    cycleCounter++;
    
    log(`🤖 [Humanizer] Cycle ${cycleData.cycleNumber} (#${cycleCounter}) - Buy: ${buySize} @ ${lastAskPrice.toFixed(6)} ($${availableAmount.toFixed(2)}) at ${timeStr}`);
    
    const buyResult = await placeGridOrder(currentTokenMeta, lastAskPrice, buySize, true);
    if (buyResult) {
      // Mettre à jour les données du cycle
      cycleData.status = 'active';
      cycleData.currentPosition = 'buy';
      cycleData.entryPrice = lastAskPrice;
      cycleData.entryTime = Date.now();
      cycleData.entryTimeStr = timeStr;
      cycleData.buySize = buySize;
      cycleData.actualAmount = availableAmount; // Montant réel utilisé
      
      // Enregistrer dans les cycles actifs
      activeCycles.set(cycleData.cycleNumber, cycleData);
      
      // Programmer la vente aléatoire pour ce cycle
      scheduleIndependentCycleSell(cycleData);
      
      log(`✅ [Humanizer] Cycle ${cycleData.cycleNumber} (#${cycleCounter}) - Buy executed - Entry price: ${lastAskPrice.toFixed(6)}`);
    }
  } catch (error) {
    log(`❌ [Humanizer] Cycle ${cycleData.cycleNumber} - Erreur d'achat: ${error.message}`);
  }
}


/**
 * Programme une vente aléatoire pour un cycle spécifique
 */
function scheduleIndependentCycleSell(cycleData) {
  // Calculer un délai aléatoire pour la vente
  let randomMinutes, randomDelay;
  
  if (holdingDurationMin === 0 && holdingDurationMax === 0) {
    // Si les deux valeurs sont 0, délai très court (1-5 secondes)
    randomMinutes = Math.random() * 4 + 1; // 1-5 secondes
    randomDelay = randomMinutes * 1000; // Convertir en millisecondes
    log(`🤖 [Humanizer] Cycle ${cycleData.cycleNumber} - Sell scheduled in ${randomMinutes.toFixed(1)} seconds (holding duration = 0)`);
  } else if (holdingDurationMin === holdingDurationMax) {
    // Si min = max, délai fixe
    randomMinutes = holdingDurationMin;
    randomDelay = randomMinutes * 60 * 1000;
    if (randomMinutes < 1) {
      const seconds = Math.round(randomMinutes * 60);
      log(`🤖 [Humanizer] Cycle ${cycleData.cycleNumber} - Sell scheduled in ${seconds} seconds (fixed delay)`);
    } else {
      log(`🤖 [Humanizer] Cycle ${cycleData.cycleNumber} - Sell scheduled in ${randomMinutes} minutes (fixed delay)`);
    }
  } else {
    // Délai aléatoire normal
    randomMinutes = Math.random() * (holdingDurationMax - holdingDurationMin) + holdingDurationMin;
    randomDelay = randomMinutes * 60 * 1000;
    if (randomMinutes < 1) {
      const seconds = Math.round(randomMinutes * 60);
      log(`🤖 [Humanizer] Cycle ${cycleData.cycleNumber} - Sell scheduled in ${seconds} seconds`);
    } else {
      log(`🤖 [Humanizer] Cycle ${cycleData.cycleNumber} - Sell scheduled in ${randomMinutes.toFixed(1)} minutes`);
    }
  }
  
  // Calculer l'heure de vente prévue
  const sellTime = new Date(Date.now() + randomDelay);
  const sellTimeStr = sellTime.toLocaleTimeString('fr-FR', { hour12: false });
  
  log(`🤖 [Humanizer] Cycle ${cycleData.cycleNumber} - Vente vers ${sellTimeStr}`);
  
  const sellTimeout = setTimeout(() => {
    if (cycleData.status === 'active' && isBotRunning) {
      log(`⏰ [Humanizer] Cycle ${cycleData.cycleNumber} - Sell delay reached - Executing sell`);
      executeIndependentCycleSell(cycleData, "time");
    }
  }, randomDelay);
  
  // Mettre à jour les données du cycle
  cycleData.sellTimeout = sellTimeout;
  cycleData.sellTimeStr = sellTimeStr;
}

/**
 * Vérifie les conditions de vente pour tous les cycles actifs
 */
async function checkAllActiveCycles() {
  for (const [cycleNumber, cycleData] of activeCycles) {
    if (cycleData.status === 'active' && cycleData.currentPosition === 'buy') {
      await checkIndependentCycleSellConditions(cycleData);
    }
  }
}

/**
 * Vérifie les conditions de vente pour un cycle indépendant
 */
async function checkIndependentCycleSellConditions(cycleData) {
  if (!cycleData || !lastBidPrice) {
    log(`⚠️ [Humanizer] Cycle ${cycleData.cycleNumber} - Missing data: cycleData=${!!cycleData}, lastBidPrice=${lastBidPrice}`);
    return;
  }
  
  // Calculer la variation de prix par rapport au prix d'entrée
  const priceVariation = Math.abs((lastBidPrice - cycleData.entryPrice) / cycleData.entryPrice) * 100;
  
  // Log de debug pour voir les variations (réduit la fréquence)
  if (cycleData.cycleNumber === 1 && Math.random() < 0.1) { // Log seulement 10% du temps pour éviter le spam
    log(`🔍 [Humanizer] Cycle ${cycleData.cycleNumber} - Current price: ${lastBidPrice.toFixed(6)}, Entry price: ${cycleData.entryPrice.toFixed(6)}, Variation: ${priceVariation.toFixed(2)}%, Threshold: ${maxVariation}%`);
  }
  
  // Vérifier si la variation dépasse le seuil
  if (priceVariation >= maxVariation) {
    log(`📈 [Humanizer] Cycle ${cycleData.cycleNumber} - Price variation detected: ${priceVariation.toFixed(2)}% (threshold: ${maxVariation}%)`);
    await executeIndependentCycleSell(cycleData, "price");
  }
}

/**
 * Exécute la vente pour un cycle indépendant
 */
async function executeIndependentCycleSell(cycleData, reason) {
  log(`🚀 [Humanizer] executeIndependentCycleSell called - Cycle: ${cycleData.cycleNumber}, Reason: ${reason}`);
  
  if (!lastBidPrice) {
    log(`❌ [Humanizer] Cycle ${cycleData.cycleNumber} - Prix bid manquant: ${lastBidPrice}`);
    return;
  }
  
  try {
    // Utiliser le montant réel de l'achat (actualAmount) au lieu du budget restant
    const sellAmount = cycleData.actualAmount || cycleData.remainingBudget;
    const sellSize = (sellAmount / lastBidPrice).toFixed(currentTokenMeta.szDecimals);
    
    const currentTime = new Date();
    const timeStr = currentTime.toLocaleTimeString('fr-FR', { hour12: false });
    
    log(`🤖 [Humanizer] Cycle ${cycleData.cycleNumber} - Sell (${reason}): ${sellSize} @ ${lastBidPrice.toFixed(6)} ($${sellAmount.toFixed(2)}) at ${timeStr}`);
    
    const sellResult = await placeGridOrder(currentTokenMeta, lastBidPrice, sellSize, false);
    if (sellResult) {
      log(`✅ [Humanizer] Cycle ${cycleData.cycleNumber} - Sell executed - Reason: ${reason}`);
      
      // Calculer le profit/perte basé sur le montant réel
      const profit = (lastBidPrice - cycleData.entryPrice) * parseFloat(sellSize);
      const profitPercent = ((lastBidPrice - cycleData.entryPrice) / cycleData.entryPrice) * 100;
      
      // Afficher le résumé du cycle
      log(`📊 [Humanizer] Cycle ${cycleData.cycleNumber} (#${cycleCounter}) completed - Buy: ${cycleData.entryTimeStr}, Sell: ${timeStr}`);
      log(`💰 [Humanizer] Cycle ${cycleData.cycleNumber} - Profit: $${profit.toFixed(2)} (${profitPercent.toFixed(2)}%)`);
      
      // Mettre à jour le budget du cycle
      cycleData.remainingBudget += profit;
      cycleData.currentPosition = null;
      cycleData.entryPrice = null;
      cycleData.entryTime = null;
      
      // Nettoyer les timeouts
      if (cycleData.sellTimeout) {
        clearTimeout(cycleData.sellTimeout);
        cycleData.sellTimeout = null;
      }
      
      // Retirer des cycles actifs
      activeCycles.delete(cycleData.cycleNumber);
      
      // Vérifier si le cycle peut continuer
      if (cycleData.remainingBudget > 0) {
        // Relancer le cycle avec un nouveau délai aléatoire
        cycleData.status = 'waiting';
        await startIndependentCycle(cycleData);
      } else {
        log(`🏁 [Humanizer] Cycle ${cycleData.cycleNumber} - Budget exhausted, cycle completed`);
        cycleData.status = 'completed';
      }
      
    } else {
      log(`❌ [Humanizer] Cycle ${cycleData.cycleNumber} - Sell failed (sellResult: ${sellResult})`);
    }
  } catch (error) {
    log(`❌ [Humanizer] Cycle ${cycleData.cycleNumber} - Erreur de vente: ${error.message}`);
  }
}


/**
 * Réinitialise l'état du mode Humanizer
 */
function resetHumanizerState() {
  // Réinitialiser les variables globales
  entryPrice = null;
  entryTime = null;
  sellScheduled = false;
  
  // Clear all timeouts immediately
  if (sellTimeout) {
    clearTimeout(sellTimeout);
    sellTimeout = null;
  }
  
  // Nettoyer tous les cycles actifs et leurs timeouts
  for (const [cycleNumber, cycleData] of activeCycles) {
    if (cycleData.sellTimeout) {
      clearTimeout(cycleData.sellTimeout);
      cycleData.sellTimeout = null;
    }
    if (cycleData.buyTimeout) {
      clearTimeout(cycleData.buyTimeout);
      cycleData.buyTimeout = null;
    }
  }
  activeCycles.clear();
  
  // Nettoyer tous les cycles du tableau et leurs timeouts
  for (const cycleData of cycleTable) {
    if (cycleData.sellTimeout) {
      clearTimeout(cycleData.sellTimeout);
      cycleData.sellTimeout = null;
    }
    if (cycleData.buyTimeout) {
      clearTimeout(cycleData.buyTimeout);
      cycleData.buyTimeout = null;
    }
  }
  cycleTable = [];
  
  // Nettoyer le timeout du prochain achat
  if (nextBuyTimeout) {
    clearTimeout(nextBuyTimeout);
    nextBuyTimeout = null;
  }
  
  // Réinitialiser les compteurs
  totalCycles = 0;
  currentCycle = 0;
  isWaitingForNextCycle = false;
  cycleCounter = 0;
  
  log(`🔄 [Humanizer] State reset - All cycles and timeouts cleaned`);
}

/**
 * Checks and cancels old orders
 */
async function checkAndCancelOldOrders() {
  // For simplicity, cancel all active orders each cycle
  // In a more advanced version, we could check open orders via API
  for (const [orderId, orderData] of activeOrders) {
    try {
      // Cancel order (simulation - in real version, use API)
      log(`🔄 Canceling order ${orderId}`);
      activeOrders.delete(orderId);
    } catch (error) {
      log(`❌ Error canceling order ${orderId}: ${error.message}`);
    }
  }
}

/**
 * Places grid trading orders
 */
async function placeGridOrders() {
  // IMMEDIATELY check if bot is still running
  if (!isBotRunning) {
    return;
  }
  
  const gridSize = parseFloat(document.getElementById("grid-size").value);
  
  if (!gridSize || gridSize <= 0) {
    log("❌ Invalid size in $ per trade");
    return;
  }
  
  // Check if we have valid prices and token metadata
  if (!lastBidPrice || !lastAskPrice || !currentTokenMeta) {
    log("❌ Missing price data or token metadata");
    return;
  }
  
  try {
    // Double check if bot is still running before calculating sizes
    if (!isBotRunning) {
      return;
    }
    
    // Calculate sizes based on USD amount
    const buySize = (gridSize / lastAskPrice).toFixed(currentTokenMeta.szDecimals);
    const sellSize = (gridSize / lastBidPrice).toFixed(currentTokenMeta.szDecimals);
    
    // Place a buy order at ASK price (for immediate execution)
    const buyOrderId = `grid_buy_${++orderCounter}`;
    log(`🟢 Placing BUY order: ${buySize} @ ${lastAskPrice.toFixed(6)} ($${gridSize})`);
    
    try {
      const buyResult = await placeGridOrder(currentTokenMeta, lastAskPrice, buySize, true);
      if (buyResult) {
        activeOrders.set(buyOrderId, {
          side: 'buy',
          price: lastAskPrice,
          size: buySize,
          amount: gridSize
        });
        log(`✅ BUY order placed: ${buyOrderId}`);
      }
    } catch (error) {
      if (isBotRunning) {
        log(`❌ BUY order error: ${error.message}`);
      }
    }
    
    // Wait a bit before placing sell order
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    // Check again if bot is still running before placing sell order
    if (!isBotRunning) {
      return;
    }
    
    // Place a sell order at BID price (for immediate execution)
    const sellOrderId = `grid_sell_${++orderCounter}`;
    log(`🔴 Placing SELL order: ${sellSize} @ ${lastBidPrice.toFixed(6)} ($${gridSize})`);
    
    try {
      const sellResult = await placeGridOrder(currentTokenMeta, lastBidPrice, sellSize, false);
      if (sellResult) {
        activeOrders.set(sellOrderId, {
          side: 'sell',
          price: lastBidPrice,
          size: sellSize,
          amount: gridSize
        });
        log(`✅ SELL order placed: ${sellOrderId}`);
      }
    } catch (error) {
      if (isBotRunning) {
        log(`❌ SELL order error: ${error.message}`);
      }
    }
    
  } catch (error) {
    if (isBotRunning) {
      log(`❌ Grid orders placement error: ${error.message}`);
    }
  }
}

/**
 * Places an IOC order with original price first, then fallback with deltas if it fails
 */
async function placeIOCOrderWithFallback(tokenMeta, basePrice, size, isBuy) {
  // IMMEDIATELY check if bot is still running
  if (!isBotRunning) {
    return false;
  }
  
  // First try: Original logic - order at exact bid/ask price (no delta)
  log(`🎯 Attempting IOC order at original price: ${basePrice.toFixed(6)}`);
  
  try {
    const success = await executeIOCOrder(tokenMeta, basePrice, size, isBuy);
    if (success) {
      log(`✅ IOC order successful at original price`);
      return true;
    }
  } catch (error) {
    log(`⚠️ IOC order failed at original price: ${error.message}`);
  }
  
  // Fallback system: Try with increasing deltas only if original order failed
  log(`🔄 Starting fallback system with deltas...`);
  const deltaLevels = [0.001, 0.0015, 0.002, 0.0025, 0.003]; // 0.1%, 0.15%, 0.2%, 0.25%, 0.3%
  
  for (let i = 0; i < deltaLevels.length; i++) {
    const delta = deltaLevels[i];
    let adjustedPrice;
    
    // Calculate price with delta
    if (isBuy) {
      // For buy orders: add delta to ensure execution (pay slightly more)
      adjustedPrice = basePrice * (1 + delta);
    } else {
      // For sell orders: subtract delta to ensure execution (receive slightly less)
      adjustedPrice = basePrice * (1 - delta);
    }
    
    const deltaPercent = (delta * 100).toFixed(2);
    log(`🎯 Fallback attempt with ${deltaPercent}% delta: ${adjustedPrice.toFixed(6)}`);
    
    try {
      const success = await executeIOCOrder(tokenMeta, adjustedPrice, size, isBuy);
      if (success) {
        log(`✅ IOC fallback successful with ${deltaPercent}% delta`);
        return true;
      }
    } catch (error) {
      log(`❌ IOC fallback error with ${deltaPercent}% delta: ${error.message}`);
      // Continue to next delta level
    }
  }
  
  log(`❌ All IOC attempts failed (original + fallbacks)`);
  return false;
}

/**
 * Executes a single IOC order attempt
 */
async function executeIOCOrder(tokenMeta, price, size, isBuy) {
  // Restore agent if needed
  const privKey = localStorage.getItem("agentPrivKey");
  const agentAddress = localStorage.getItem("agentAddress");
  if (!privKey || !agentAddress) throw new Error("No agent found");
  
  const agentWallet = new ethers.Wallet(privKey);
  
  // EOA (just in case)
  if (!mainAddress) {
    const provider = new ethers.BrowserProvider(window.ethereum);
    const signer = await provider.getSigner();
    mainAddress = await signer.getAddress();
  }
  
  // Client via agent
  const exchangeViaAgent = new hl.ExchangeClient({
    wallet: agentWallet.privateKey,
    transport: getTransport(),
  });
  
  const order = {
    a: tokenMeta.market_index,
    b: isBuy,  // true for buy, false for sell
    p: price.toString(),
    s: size,
    r: false,
    t: { limit: { tif: "Ioc" } },
  };
  
  // Configuration du builder selon le protocole actuel
  const currentProtocol = window.currentProtocol || "based";
  const protocolConfig = PROTOCOL_CONFIG[currentProtocol];
  const builderParams = {
    b: protocolConfig.builderAddress,
    f: protocolConfig.feeValue
  };
  
  const resp = await exchangeViaAgent.order({ 
    orders: [order], 
    grouping: "na",
    builder: builderParams
  });
  
  if (resp?.status !== "ok") {
    throw new Error("Order failed: " + JSON.stringify(resp));
  }
  
  return true;
}

/**
 * Places a grid order (reuses existing logic with IOC fallback)
 */
async function placeGridOrder(tokenMeta, price, size, isBuy) {
  return await placeIOCOrderWithFallback(tokenMeta, price, size, isBuy);
}

/**
 * Starts the grid trading bot
 */
export async function startGridBot() {
  try {
    const select = document.getElementById("token-select");
    if (!select.selectedOptions[0]) {
      throw new Error("Please select a token");
    }
    
    currentTokenMeta = JSON.parse(select.selectedOptions[0].dataset.meta);
    const gridSize = parseFloat(document.getElementById("grid-size").value);
    
    if (!gridSize || gridSize <= 0) {
      throw new Error("Please enter a valid size in $ per trade");
    }
    
    // Check that an agent exists
    const privKey = localStorage.getItem("agentPrivKey");
    if (!privKey) {
      throw new Error("Please create an agent wallet first");
    }
    
    // Validate humanizer settings if enabled
    const humanizerSettings = getHumanizerSettings();
    if (humanizerSettings.enabled) {
      if (!humanizerSettings.maxVariation || humanizerSettings.maxVariation <= 0) {
        throw new Error("Please enter a valid max variation percentage for Humanizer mode");
      }
      if (humanizerSettings.holdingDurationMin === undefined || humanizerSettings.holdingDurationMax === undefined || 
          humanizerSettings.holdingDurationMin < 0 || humanizerSettings.holdingDurationMax < 0 ||
          humanizerSettings.holdingDurationMin > humanizerSettings.holdingDurationMax) {
        throw new Error("Please enter valid holding duration range (min <= max) for Humanizer mode");
      }
    }
    
    log(`🚀 Starting grid trading bot for ${currentTokenMeta.name}`);
    log(`💰 Size per trade: $${gridSize}`);
    
    if (humanizerSettings.enabled) {
      const usdcBalance = getCurrentUSDCBalance();
      const maxCycles = calculateMaxCycles(usdcBalance, gridSize);
      
      log(`🤖 Humanizer mode enabled - Max variation: ${humanizerSettings.maxVariation}%, Holding: ${humanizerSettings.holdingDurationMin}-${humanizerSettings.holdingDurationMax} min`);
      log(`🔄 Cycles multiples: ${maxCycles} cycles possibles avec ${usdcBalance.toFixed(2)} USDC`);
    }
    
    // Connect to WebSocket
    await connectWebSocket(currentTokenMeta);
    
    // Start bot
    isBotRunning = true;
    updateBotStatus("Running", "#27ae60");
    
    // Start timer if duration is specified
    startBotTimer();
    
    // Hide start button and show stop button
    document.getElementById("start-bot").style.display = "none";
    document.getElementById("stop-bot").style.display = "inline-block";
    
    log("✅ Bot started successfully");
    
  } catch (error) {
    log(`❌ Bot startup error: ${error.message}`);
    throw error;
  }
}

/**
 * Stops the grid trading bot
 */
export function stopGridBot() {
  try {
    // IMMEDIATELY stop all trading activities
    isBotRunning = false;
    
    // Stop timer
    stopBotTimer();
    
    // Close WebSocket immediately to stop price updates
    if (ws) {
      ws.close();
      ws = null;
    }
    
    // Clear WebSocket reconnection intervals
    if (wsReconnectInterval) {
      clearTimeout(wsReconnectInterval);
      wsReconnectInterval = null;
    }
    wsReconnectAttempts = 0;
    
    // Cancel all active orders
    activeOrders.clear();
    
    // Reset prices to prevent any remaining trading logic
    lastBidPrice = null;
    lastAskPrice = null;
    
    // Reset humanizer state and clear all timeouts
    resetHumanizerState();
    
    // Update interface
    updateBotStatus("Stopped", "#e74c3c");
    document.getElementById("current-prices").textContent = "Not connected";
    
    // Hide stop button and show start button
    document.getElementById("start-bot").style.display = "inline-block";
    document.getElementById("stop-bot").style.display = "none";
    
    log("⏹️ Bot stopped");
    
    // Wait longer to ensure all trading processes are completely stopped
    setTimeout(async () => {
      log("🔄 Starting final token sell process...");
      await sellCurrentTokenToUSDC();
    }, 3000); // Wait 3 seconds to ensure all processes are stopped
    
  } catch (error) {
    log(`❌ Bot stop error: ${error.message}`);
  }
}

/**
 * Updates bot status in the interface
 */
function updateBotStatus(status, color) {
  const statusElement = document.getElementById("status-text");
  const statusContainer = document.getElementById("bot-status");
  
  if (statusElement) {
    statusElement.textContent = status;
  }
  
  if (statusContainer) {
    statusContainer.style.background = color === "#27ae60" ? "#e8f5e8" : "#f8f9fa";
  }
}

/**
 * Starts the bot timer
 */
function startBotTimer() {
  const durationInput = document.getElementById("run-duration");
  const duration = parseFloat(durationInput.value);
  
  if (duration && duration > 0) {
    botDuration = duration; // in minutes
    botStartTime = Date.now();
    
    // Show timer display
    const timerDisplay = document.getElementById("timer-display");
    if (timerDisplay) {
      timerDisplay.style.display = "block";
    }
    
    // Start timer interval (update every second)
    timerInterval = setInterval(updateTimer, 1000);
    
    log(`⏰ Bot timer started: ${duration} minutes`);
  }
}

/**
 * Updates the timer display
 */
function updateTimer() {
  if (!botStartTime || !botDuration) return;
  
  const elapsed = Date.now() - botStartTime;
  const elapsedMinutes = elapsed / (1000 * 60);
  const remainingMinutes = botDuration - elapsedMinutes;
  
  if (remainingMinutes <= 0) {
    // Time's up - stop the bot
    log("⏰ Bot timer expired - stopping bot automatically");
    stopGridBot();
    return;
  }
  
  // Update display
  const minutes = Math.floor(remainingMinutes);
  const seconds = Math.floor((remainingMinutes - minutes) * 60);
  const timeString = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
  
  const timeRemainingElement = document.getElementById("time-remaining");
  if (timeRemainingElement) {
    timeRemainingElement.textContent = timeString;
  }
}

/**
 * Stops the bot timer
 */
function stopBotTimer() {
  if (timerInterval) {
    clearInterval(timerInterval);
    timerInterval = null;
  }
  
  botStartTime = null;
  botDuration = null;
  
  // Hide timer display
  const timerDisplay = document.getElementById("timer-display");
  if (timerDisplay) {
    timerDisplay.style.display = "none";
  }
  
  const timeRemainingElement = document.getElementById("time-remaining");
  if (timeRemainingElement) {
    timeRemainingElement.textContent = "--:--";
  }
}

/**
 * Disconnects the wallet and clears all stored data
 */
export function disconnectWallet() {
  try {
    // Stop any running bot
    if (isBotRunning) {
      stopGridBot();
    }
    
    // Stop wallet balance WebSocket
    stopWalletBalanceWebSocket();
    
    // Clear localStorage data
    localStorage.removeItem("agentPrivKey");
    localStorage.removeItem("agentAddress");
    localStorage.removeItem("mainAddress");
    
    // Reset global variables
    agentWallet = null;
    mainAddress = null;
    isWalletConnected = false;
    
    // Update display
    updateWalletInfoDisplay();
    
    log("✅ Wallet disconnected successfully");
    
    // Only show popup if not called from page unload
    if (!window.isPageUnloading) {
      showPopup('success', 'Wallet Disconnected', 'Wallet disconnected successfully');
    }
    
  } catch (error) {
    log(`❌ Error during disconnection: ${error.message}`);
    if (!window.isPageUnloading) {
      showPopup('error', 'Disconnection Error', `Error during disconnection: ${error.message}`);
    }
  }
}

/**
 * Updates wallet info display
 */
export function updateWalletInfoDisplay() {
  const connectSection = document.getElementById("connect-section");
  const walletInfo = document.getElementById("wallet-info");
  const mainWalletAddress = document.getElementById("main-wallet-address");
  const agentWalletAddress = document.getElementById("agent-wallet-address");
  const connectButton = document.getElementById("connect");
  const disconnectButton = document.getElementById("disconnect");
  
  if (agentWallet && mainAddress) {
    // Hide connect button, show disconnect button and wallet info
    if (connectSection) connectSection.style.display = "none";
    if (walletInfo) walletInfo.style.display = "block";
    if (connectButton) connectButton.style.display = "none";
    if (disconnectButton) disconnectButton.style.display = "block";
    
    // Update addresses
    if (mainWalletAddress) {
      mainWalletAddress.textContent = `${mainAddress.substring(0, 6)}...${mainAddress.substring(mainAddress.length - 4)}`;
    }
    if (agentWalletAddress) {
      agentWalletAddress.textContent = `${agentWallet.address.substring(0, 6)}...${agentWallet.address.substring(agentWallet.address.length - 4)}`;
    }
    
    // Start wallet balance WebSocket
    startWalletBalanceWebSocket();
    
    // WebSocket will handle balance updates, no need for API fallback
  } else {
    // Show connect button, hide disconnect button and wallet info
    if (connectSection) connectSection.style.display = "block";
    if (walletInfo) walletInfo.style.display = "none";
    if (connectButton) connectButton.style.display = "block";
    if (disconnectButton) disconnectButton.style.display = "none";
    
    // Stop wallet balance WebSocket
    stopWalletBalanceWebSocket();
  }
}


/**
 * Starts WebSocket connection for wallet balance
 */
function startWalletBalanceWebSocket() {
  if (!mainAddress || isWalletConnected) return;
  
  try {
    const wsUrl = IS_MAINNET ? "wss://api.hyperliquid.xyz/ws" : "wss://api.hyperliquid-testnet.xyz/ws";
    
    log(`🔌 Connecting to wallet balance WebSocket for ${mainAddress}`);
    
    walletWs = new WebSocket(wsUrl);
    
    walletWs.onopen = () => {
      log("✅ Wallet balance WebSocket connected");
      isWalletConnected = true;
      
      // Wait a bit to ensure WebSocket is fully ready
      setTimeout(() => {
        if (walletWs && walletWs.readyState === WebSocket.OPEN) {
          // Subscribe to user data
          const subscribeMsg = {
            method: "subscribe",
            subscription: {
              type: "webData2",
              user: mainAddress
            }
          };
          
          walletWs.send(JSON.stringify(subscribeMsg));
          log(`📡 Subscribed to wallet data: ${JSON.stringify(subscribeMsg)}`);
        } else {
          log("❌ WebSocket not ready for sending");
        }
      }, 100);
    };
    
    walletWs.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        if (data.channel === "webData2" && data.data) {
          // Extract USDC balance from spotState.balances
          const spotState = data.data.spotState || {};
          const balances = spotState.balances || [];
          let usdcBalance = 0;
          
          for (const balance of balances) {
            if (balance.coin === "USDC") {
              usdcBalance = parseFloat(balance.total) || 0;
              break;
            }
          }
          
          // Update USDC balance display
          const usdcBalanceElement = document.getElementById("usdc-balance");
          const balanceStatusElement = document.getElementById("balance-status");
          
          if (usdcBalanceElement) {
            usdcBalanceElement.textContent = `${usdcBalance.toFixed(2)} USDC`;
            usdcBalanceElement.style.color = "#27ae60"; // Green color for live data
          }
          
          if (balanceStatusElement) {
            balanceStatusElement.textContent = "(live)";
            balanceStatusElement.style.color = "#27ae60";
          }
        }
      } catch (error) {
        log(`❌ Wallet data parsing error: ${error.message}`);
      }
    };
    
    walletWs.onerror = (error) => {
      log(`❌ Wallet balance WebSocket error: ${error}`);
      isWalletConnected = false;
    };
    
    walletWs.onclose = () => {
      log("🔌 Wallet balance WebSocket closed");
      isWalletConnected = false;
      
      // Attempt to reconnect if user is still connected
      if (mainAddress && agentWallet) {
        attemptWalletWebSocketReconnection();
      }
    };
    
    // WebSocket timeout handling - just log the issue
    setTimeout(() => {
      if (!isWalletConnected) {
        log("⚠️ WebSocket connection timeout");
      }
    }, 5000);
    
  } catch (error) {
    log(`❌ Error starting wallet balance WebSocket: ${error.message}`);
  }
}

/**
 * Attempts to reconnect the wallet WebSocket
 */
function attemptWalletWebSocketReconnection() {
  if (walletWsReconnectAttempts >= maxWalletWsReconnectAttempts) {
    log(`❌ Maximum wallet WebSocket reconnection attempts reached (${maxWalletWsReconnectAttempts})`);
    return;
  }
  
  walletWsReconnectAttempts++;
  const delay = Math.min(1000 * Math.pow(2, walletWsReconnectAttempts - 1), 30000); // Exponential backoff, max 30s
  
  log(`🔄 Attempting wallet WebSocket reconnection ${walletWsReconnectAttempts}/${maxWalletWsReconnectAttempts} in ${delay/1000}s...`);
  
  walletWsReconnectInterval = setTimeout(() => {
    if (mainAddress && agentWallet && !isWalletConnected) {
      startWalletBalanceWebSocket();
      walletWsReconnectAttempts = 0; // Reset counter on successful reconnection
    }
  }, delay);
}

/**
 * Stops WebSocket connection for wallet balance
 */
function stopWalletBalanceWebSocket() {
  if (walletWs) {
    walletWs.close();
    walletWs = null;
  }
  isWalletConnected = false;
  
  // Clear reconnection intervals
  if (walletWsReconnectInterval) {
    clearTimeout(walletWsReconnectInterval);
    walletWsReconnectInterval = null;
  }
  walletWsReconnectAttempts = 0;
  
  // Reset USDC balance display
  const usdcBalanceElement = document.getElementById("usdc-balance");
  const balanceStatusElement = document.getElementById("balance-status");
  
  if (usdcBalanceElement) {
    usdcBalanceElement.textContent = "--";
    usdcBalanceElement.style.color = ""; // Reset color
  }
  
  if (balanceStatusElement) {
    balanceStatusElement.textContent = "(loading...)";
    balanceStatusElement.style.color = ""; // Reset color
  }
}
