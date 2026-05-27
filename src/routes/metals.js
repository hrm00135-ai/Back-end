const express = require('express');
const router = express.Router();
const { Op } = require('sequelize');
const { MetalPrice, MetalPriceHistory } = require('../models');
const { jwtRequired, requireRole, successResponse, errorResponse } = require('../utils/helpers');
const config = require('../config/config');
const https = require('https');

// ────────────────────────────────────────────────────────────
// Fetch metal price from GoldAPI
// ────────────────────────────────────────────────────────────
async function fetchFromGoldApi(metalSymbol) {
  return new Promise((resolve, reject) => {
    const url = `https://www.goldapi.io/api/${metalSymbol}/INR`;
    const options = {
      hostname: 'www.goldapi.io',
      path: `/api/${metalSymbol}/INR`,
      method: 'GET',
      headers: { 'x-access-token': config.METAL_API_KEY, 'Content-Type': 'application/json' },
    };
    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); } catch (e) { reject(e); }
      });
    });
    req.on('error', reject);
    req.end();
  });
}

// ────────────────────────────────────────────────────────────
// GET CURRENT METAL PRICES
// ────────────────────────────────────────────────────────────
router.get('/', jwtRequired, async (req, res) => {
  try {
    const prices = await MetalPrice.findAll({ order: [['fetched_at', 'DESC']] });
    return successResponse(res, { data: prices.map(p => p.toDict()) });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// FETCH & STORE LIVE PRICES (admin)
// ────────────────────────────────────────────────────────────
router.post('/fetch', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    if (!config.METAL_API_KEY) return errorResponse(res, 'METAL_API_KEY not configured', 503);

    const metals = [
      { symbol: 'XAU', name: 'gold', purities: ['24K', '22K', '18K'] },
      { symbol: 'XAG', name: 'silver', purities: ['999', '925'] },
    ];

    const results = [];
    const today = new Date().toISOString().split('T')[0];

    for (const metal of metals) {
      try {
        const apiData = await fetchFromGoldApi(metal.symbol);
        const pricePerGramBase = apiData.price_gram_24k || (apiData.price / 31.1035);

        for (const purity of metal.purities) {
          let multiplier = 1;
          if (metal.name === 'gold') {
            if (purity === '22K') multiplier = 22 / 24;
            else if (purity === '18K') multiplier = 18 / 24;
          } else if (metal.name === 'silver') {
            if (purity === '925') multiplier = 0.925;
          }

          const pricePerGram = Math.round(pricePerGramBase * multiplier * 100) / 100;
          const pricePerKg = Math.round(pricePerGram * 1000 * 100) / 100;
          const pricePer10g = Math.round(pricePerGram * 10 * 100) / 100;

          // Upsert current price
          const [priceRecord] = await MetalPrice.findOrCreate({
            where: { metal: metal.name, purity },
            defaults: {
              metal: metal.name, purity, price_per_gram: pricePerGram,
              price_per_10gram: pricePer10g, price_per_kg: pricePerKg,
              currency: 'INR', source: 'goldapi.io', fetched_at: new Date(),
            },
          });
          priceRecord.price_per_gram = pricePerGram;
          priceRecord.price_per_10gram = pricePer10g;
          priceRecord.price_per_kg = pricePerKg;
          priceRecord.fetched_at = new Date();
          await priceRecord.save();

          // Save to history (once per day)
          try {
            await MetalPriceHistory.findOrCreate({
              where: { metal: metal.name, purity, date: today },
              defaults: {
                metal: metal.name, purity, price_per_gram: pricePerGram,
                currency: 'INR', date: today, source: 'goldapi.io',
              },
            });
          } catch {}

          results.push(priceRecord.toDict());
        }
      } catch (metalErr) {
        console.error(`[METAL FETCH] Error fetching ${metal.name}: ${metalErr.message}`);
      }
    }

    return successResponse(res, { data: results, message: `Updated ${results.length} metal prices` });
  } catch (err) {
    console.error(err);
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// MANUAL UPDATE (admin)
// ────────────────────────────────────────────────────────────
router.post('/update', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const data = req.body || {};
    if (!data.metal) return errorResponse(res, 'metal is required', 400);
    if (!data.purity) return errorResponse(res, 'purity is required', 400);
    if (data.price_per_gram === undefined) return errorResponse(res, 'price_per_gram is required', 400);

    const pricePerGram = parseFloat(data.price_per_gram);
    const pricePerKg = Math.round(pricePerGram * 1000 * 100) / 100;
    const pricePer10g = Math.round(pricePerGram * 10 * 100) / 100;

    const [record] = await MetalPrice.findOrCreate({
      where: { metal: data.metal, purity: data.purity },
      defaults: {
        metal: data.metal, purity: data.purity, price_per_gram: pricePerGram,
        price_per_10gram: pricePer10g, price_per_kg: pricePerKg,
        currency: 'INR', source: 'manual', fetched_at: new Date(),
      },
    });
    record.price_per_gram = pricePerGram;
    record.price_per_10gram = pricePer10g;
    record.price_per_kg = pricePerKg;
    record.source = 'manual';
    record.fetched_at = new Date();
    await record.save();

    // Save to history
    const today = new Date().toISOString().split('T')[0];
    await MetalPriceHistory.findOrCreate({
      where: { metal: data.metal, purity: data.purity, date: today },
      defaults: {
        metal: data.metal, purity: data.purity, price_per_gram: pricePerGram,
        currency: 'INR', date: today, source: 'manual',
      },
    });

    return successResponse(res, { data: record.toDict(), message: 'Metal price updated' });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// PRICE HISTORY
// ────────────────────────────────────────────────────────────
router.get('/history', jwtRequired, async (req, res) => {
  try {
    const where = {};
    if (req.query.metal) where.metal = req.query.metal;
    if (req.query.purity) where.purity = req.query.purity;
    if (req.query.from_date) where.date = { ...(where.date || {}), [Op.gte]: req.query.from_date };
    if (req.query.to_date) where.date = { ...(where.date || {}), [Op.lte]: req.query.to_date };

    const history = await MetalPriceHistory.findAll({
      where, order: [['date', 'DESC']], limit: 365,
    });
    return successResponse(res, { data: history.map(h => h.toDict()) });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

module.exports = router;
