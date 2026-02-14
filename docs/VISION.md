# Heavymeta Collective — Vision

## What It Is

The Heavymeta Collective is a cooperative onboarding platform that combines blockchain identity, decentralized content, and peer-to-peer payments into a single web application. It is the front door to the Heavymeta ecosystem — a network of artists, builders, and creators who co-own infrastructure rather than renting it from platforms.

## The Problem

Creative communities today are fragmented across platforms they don't control. Link-in-bio tools are centralized. Payment rails take 15-30% cuts. Identity is siloed per service. Artists can't own their audience graph, their payment infrastructure, or their content distribution.

## The Solution

Heavymeta Collective gives every member:

1. **A self-sovereign identity** — a Stellar keypair created at enrollment, encrypted with dual-key (Banker + Guardian) security, stored in the app's database. The member's public address is their on-chain identity across all Heavymeta services.

2. **A decentralized link-tree** — profile content (links, colors, avatar, QR codes, wallet addresses) published as JSON to IPFS and made permanently addressable via IPNS. No central server required to serve a member's profile.

3. **Native crypto payments** — members can receive XLM via branded QR codes, send XLM from their in-app wallet, and create disposable denomination wallets (1-21 XLM, Fibonacci scale) for quick peer-to-peer transactions with automatic settlement.

4. **A cooperative membership** — paid members (333 XLM or equivalent USD via Stripe) are registered on-chain via the `hvym_roster` Soroban smart contract. This on-chain roster is the source of truth for membership across the ecosystem.

5. **Pintheon node credentials** — coop members can generate launch tokens and keys to run a Pintheon node, the cooperative's distributed compute layer. Node operators earn by providing services to the network.

## Membership Tiers

### Free Member
- Personalized link-tree (IPFS/IPNS-backed)
- Custom color theme (light + dark palettes)
- Public profile at `/lt/{ipns_name}`
- QR code for profile sharing

### Coop Member (Paid)
Everything in Free, plus:
- Stellar wallet (balance, send, receive)
- Denomination wallets for peer payments
- NFC card design upload + card case (peer card collection)
- On-chain roster registration (Soroban contract)
- Pintheon launch token/key generation
- 3D QR code viewer

## Payment Model

- **Crypto path:** 333 XLM sent to the Collective's Banker address. Detected via Horizon polling, verified by memo match.
- **Fiat path:** Dynamic USD price (2x the XLM market value) via Stripe hosted checkout. Webhook confirms payment and triggers enrollment.
- **Denomination wallet fees:** 3% on received payments, automatically deducted during AccountMerge settlement. Revenue goes to the Collective treasury (Banker account).

## Network Architecture

The app is designed testnet-first, mainnet-ready. A single environment variable (`STELLAR_NETWORK`) switches the entire stack — Horizon endpoints, Soroban RPC, network passphrase, and block explorer links. All development happens on Stellar testnet; production deployment changes one variable.

## Adjacent Systems

| System | Repo | Role |
|--------|------|------|
| **hvym_stellar** | `../hvym_stellar` | Shared-key encryption library (X25519 ECDH, token builders, key derivation) |
| **Pintheon Contracts** | `../pintheon_contracts` | Soroban smart contracts (roster, collective, pin service, opus token) |
| **Pintheon Node** | `../pintheon` | Distributed compute node that consumes launch tokens from this app |

## Design Principles

- **Encryption by default.** User secrets never exist in plaintext in the database. Dual-key architecture means a single compromised key cannot decrypt user wallets.
- **IPFS as the content layer.** SQLite is the index; IPFS is the delivery network. Public profiles work without the app server being online.
- **Async throughout.** Every I/O operation (database, Horizon, IPFS, Stripe, email) is non-blocking. The app handles concurrent users on a single process.
- **Progressive disclosure.** Free members see link-tree tools. Coop features (wallets, cards, launch) appear only after payment. No feature overload at signup.
- **One codebase, two networks.** No mainnet fork, no separate deployment configs. Testnet and mainnet share identical code paths.
