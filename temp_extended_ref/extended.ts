// Interface for referral user data
export interface ReferralUser {
  firstTradedOn: number;
  wallet: string;
  rebate: string;
  tradedVolume: string;
  totalFees: string;
}

export interface ReferralDashboardResponse {
  referralLinkToDirectKeyMetrics: Record<string, unknown>;
  subaffiliateToKeyMetrics: Record<string, unknown>;
  activeSubaffiliates: {
    current: number;
    previous: number;
  };
  affiliates: Array<{
    clientId: number;
    name: string;
    onboarded: number;
    mainGroup: Record<string, unknown>;
  }>;
  users: ReferralUser[];
  daily: Record<string, unknown>[];
  weekly: Record<string, unknown>[];
  monthly: Record<string, unknown>[];
}

// Decrypt subaccount private key using NaCl (same logic as L2 keys)
export async function decryptSubaccountPrivateKey(encryptedKeyData: string, privateKeyHex: string): Promise<string> {
  try {
    // Parse the JSON data to extract ciphertext, nonce, and sender public key
    const encryptedKeyObj = JSON.parse(encryptedKeyData);
    const { ciphertext, nonce, sender_public_key } = encryptedKeyObj;
    
    if (!ciphertext || !nonce || !sender_public_key) {
      throw new Error('Missing required fields in encrypted key data');
    }
    
    // Import tweetnacl for decryption
    const nacl = await import('tweetnacl');
    const naclUtil = await import('tweetnacl-util');
    
    // Convert hex strings to Uint8Array
    const backendPrivateKey = new Uint8Array(Buffer.from(privateKeyHex.slice(2), 'hex'));
    const encryptedData = new Uint8Array(Buffer.from(ciphertext.slice(2), 'hex')); // Remove 0x prefix
    const nonceData = new Uint8Array(Buffer.from(nonce.slice(2), 'hex')); // Remove 0x prefix
    const senderPubKey = new Uint8Array(Buffer.from(sender_public_key.slice(2), 'hex')); // Remove 0x prefix
    
    // Decrypt using NaCl box
    const decrypted = nacl.box.open(encryptedData, nonceData, senderPubKey, backendPrivateKey);
    
    if (!decrypted) {
      throw new Error('Failed to decrypt subaccount private key');
    }
    
    // Convert back to hex string
    return naclUtil.encodeUTF8(decrypted);
  } catch (error) {
    console.error('❌ Error decrypting subaccount private key:', error);
    throw new Error('Failed to decrypt subaccount private key');
  }
}

// Decrypt L2 private key using NaCl
async function decryptL2PrivateKey(encryptedKeyData: string, privateKeyHex: string): Promise<string> {
  try {
    // Parse the JSON data to extract ciphertext, nonce, and sender public key
    const encryptedKeyObj = JSON.parse(encryptedKeyData);
    const { ciphertext, nonce, sender_public_key } = encryptedKeyObj;
    
    if (!ciphertext || !nonce || !sender_public_key) {
      throw new Error('Missing required fields in encrypted key data');
    }
    
    // Import tweetnacl for decryption
    const nacl = await import('tweetnacl');
    const naclUtil = await import('tweetnacl-util');
    
    // Convert hex strings to Uint8Array
    const backendPrivateKey = new Uint8Array(Buffer.from(privateKeyHex.slice(2), 'hex'));
    const encryptedData = new Uint8Array(Buffer.from(ciphertext.slice(2), 'hex')); // Remove 0x prefix
    const nonceData = new Uint8Array(Buffer.from(nonce.slice(2), 'hex')); // Remove 0x prefix
    const senderPubKey = new Uint8Array(Buffer.from(sender_public_key.slice(2), 'hex')); // Remove 0x prefix
    
    // Decrypt using NaCl box
    const decrypted = nacl.box.open(encryptedData, nonceData, senderPubKey, backendPrivateKey);
    
    if (!decrypted) {
      throw new Error('Failed to decrypt L2 private key');
    }
    
    // Convert back to hex string
    return naclUtil.encodeUTF8(decrypted);
  } catch (error) {
    console.error('❌ Error decrypting L2 private key:', error);
    throw new Error('Failed to decrypt L2 private key');
  }
}

// Verify if user is using DROID referral
export async function verifyDroidReferral(walletAddress: string, discordId: string): Promise<{
  isUsingDroidReferral: boolean;
  userData?: ReferralUser;
  error?: string;
}> {
  try {
    console.log('🔍 Verifying DROID referral for wallet:', walletAddress);
    
     // First, get the user's L2 private key from database
     const { supabaseAdmin } = await import('./supabase');
     
     console.log('🔍 Searching for user in extended table:', { discordId, walletAddress });
     
     const { data: dbUserData, error: userError } = await supabaseAdmin
       .from('extended') // Table name is 'extended'
       .select('L2_private')
       .eq('discord_id', discordId)
       .eq('wallet_address', walletAddress)
       .single();
     
     console.log('📊 Database query result:', { dbUserData, userError });
     
     if (userError) {
       console.error('❌ Database error:', userError);
       throw new Error(`Database error: ${userError.message}`);
     }
     
     if (!dbUserData) {
       throw new Error('User not found in extended table');
     }
     
     if (!dbUserData?.L2_private) {
       throw new Error('User L2 private key not found in database');
     }
     
     // For testing, use hardcoded API key
     const apiKey = "01e978f5abcad9851652a8eac173913e";
    
    // Decrypt the L2 private key
    const decryptedPrivateKeyHex = await decryptL2PrivateKey(
      dbUserData.L2_private,
      process.env.NACL_PRIVATE_KEY || '0xd1062b6bdaf027d6b055ddb5a2508ec3f76e078e2cd3e7eb4ebe3d0a9e2e92eb' // Private key for decryption
    );
    
     // Import starknet modules
     const { ec, hash, num } = await import('starknet');
     
     // Convert hex string to BigInt for starknet
     const l2PrivateKey = decryptedPrivateKeyHex.startsWith("0x")
         ? decryptedPrivateKeyHex
         : "0x" + decryptedPrivateKeyHex;
     
     // Derive the L2 public key
     const l2PublicKey = ec.starkCurve.getStarkKey(l2PrivateKey);
     
     // Create payload for authentication using starknetKeccak
     const payload = [
       num.toHex(hash.starknetKeccak("user")),
       num.toHex(hash.starknetKeccak("referrals")),
       num.toHex(hash.starknetKeccak("dashboard")),
       num.toHex(hash.starknetKeccak("ALL")),
     ];
     
     // Compute hash of the payload
     const payloadHash = hash.computeHashOnElements(payload);
     
     // Sign the hash with L2 private key
     const signature = ec.starkCurve.sign(l2PrivateKey, payloadHash);
    
     console.log('🔐 Sending authenticated request to Extended API...');
     
     // Call Extended API with StarkNet signature authentication
     const response = await fetch(
         "https://api.starknet.extended.exchange/api/v1/user/referrals/dashboard?period=ALL",
         {
           method: "GET",
           headers: {
             "Content-Type": "application/json",
             "User-Agent": "DroidHL_BASED/1.0", // Mandatory header
             "X-Api-Key": apiKey,
             "X-Starknet-PubKey": l2PublicKey,
             "X-Starknet-Signature": `${signature.r},${signature.s}`
           }
         }
       );

     if (!response.ok) {
       throw new Error(`Extended API error: ${response.status} - ${response.statusText}`);
     }

     const response_data = await response.json();
     console.log('📊 Complete Extended API response:', response_data);
     
     // Extract the actual data from the response
     const data: ReferralDashboardResponse = response_data.data || response_data;
     
     console.log('📊 Extended API response structure:', {
       hasUsers: !!data.users,
       usersCount: data.users?.length || 0,
       hasAffiliates: !!data.affiliates,
       affiliatesCount: data.affiliates?.length || 0
     });
     
     // Check if the response has the expected structure
     if (!data || !data.users || !Array.isArray(data.users)) {
       console.log('⚠️ Unexpected API response structure - no users array found');
       return {
         isUsingDroidReferral: false,
         error: 'API response does not contain users array'
       };
     }
     
     console.log('🔍 Searching for wallet in users list:', {
       searchWallet: walletAddress.toLowerCase(),
       totalUsers: data.users.length,
       userWallets: data.users.map(u => u.wallet.toLowerCase())
     });
     
     // Check if the wallet address is in the users list
     const userData = data.users.find(user => 
       user.wallet.toLowerCase() === walletAddress.toLowerCase()
     );

    const isUsingDroidReferral = !!userData;

    console.log('✅ DROID referral verification result:', {
      isUsingDroidReferral,
      userData: userData || null,
      totalUsersInReferral: data.users.length,
      referralInfo: {
        hasLORDORReferral: !!response_data.data?.referralLinkToDirectKeyMetrics?.LORDOR,
        activeSubaffiliates: data.activeSubaffiliates
      }
    });

    return {
      isUsingDroidReferral,
      userData: userData || undefined
    };

  } catch (error) {
    console.error('❌ Error verifying DROID referral:', error);
    return {
      isUsingDroidReferral: false,
      error: error instanceof Error ? error.message : 'Unknown error'
    };
  }
}
