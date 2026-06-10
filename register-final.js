const { chromium } = require('playwright');
const fs = require('fs');

function r(len) {
  const c = 'abcdefghijklmnopqrstuvwxyz0123456789';
  let s = '';
  for (let i = 0; i < len; i++) s += c[Math.floor(Math.random() * c.length)];
  return s;
}

function log(msg) { console.log(`[${new Date().toISOString().substring(11, 19)}] ${msg}`); }
async function delay(ms) { return new Promise(res => setTimeout(res, ms)); }

async function main() {
  const email = `deezerbot${r(8)}@outlook.com`;
  const password = `Dz${r(10)}!A1`;
  const username = `dzuser${r(6)}`;

  log(`Email: ${email} | Pass: ${password} | User: ${username}`);

  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled'],
  });

  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    locale: 'en-US',
    timezoneId: 'America/New_York',
  });

  await context.addInitScript(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => false });
  });

  const page = await context.newPage();

  try {
    log('Getting session...');
    await page.goto('https://www.deezer.com/us/', { waitUntil: 'domcontentloaded', timeout: 20000 });
    await delay(2000);

    log('Getting API token...');
    const tokenResult = await page.evaluate(async () => {
      const resp = await fetch('https://www.deezer.com/ajax/gw-light.php?method=deezer.getUserData&input=3&api_version=1.0.0&api_token=&cid=' + Math.floor(Math.random() * 999999), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ APP_NAME: 'Deezer' }),
        credentials: 'include',
      });
      return await resp.json();
    });

    const apiToken = tokenResult.results?.USER_TOKEN || '';
    log(`Token: ${apiToken.substring(0, 30)}...`);

    if (!apiToken) {
      log('ERROR: No API token');
      await browser.close();
      return;
    }

    // CREATE ACCOUNT
    log('\n=== CREATING ACCOUNT ===');
    const createResult = await page.evaluate(async (params) => {
      const { token, email, password, username } = params;
      const resp = await fetch(`https://www.deezer.com/ajax/gw-light.php?method=user.create&input=3&api_version=1.0.0&api_token=${token}&cid=${Math.floor(Math.random() * 999999)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          APP_NAME: 'Deezer',
          EMAIL: email,
          PASSWORD: password,
          BLOG_NAME: username,
          SEX: 'M',
          BIRTHDAY: '1995-06-15',
          JOURNEY_VERSION: 'unlogged_smart_and_login_web_v1',
        }),
        credentials: 'include',
      });
      return await resp.json();
    }, { token: apiToken, email, password, username });

    log(`Response: ${JSON.stringify(createResult).substring(0, 500)}`);

    if (createResult.results?.arl) {
      const arl = createResult.results.arl;
      log(`\n========== ARL: ${arl} ==========`);
      fs.writeFileSync('/tmp/deezer-register/result.json', JSON.stringify({
        email, password, username, arl, timestamp: new Date().toISOString()
      }, null, 2));
      log('Saved to result.json');
    } else if (createResult.error?.REQUEST_ERROR === 'email_already_used') {
      log('Email already used. Generating new one...');
      // The first call already registered but we lost the ARL. Try again with new email.
      const email2 = `deezerbot${r(8)}@outlook.com`;
      const createResult2 = await page.evaluate(async (params) => {
        const { token, email, password, username } = params;
        const resp = await fetch(`https://www.deezer.com/ajax/gw-light.php?method=user.create&input=3&api_version=1.0.0&api_token=${token}&cid=${Math.floor(Math.random() * 999999)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            APP_NAME: 'Deezer',
            EMAIL: email,
            PASSWORD: password,
            BLOG_NAME: username,
            SEX: 'M',
            BIRTHDAY: '1995-06-15',
            JOURNEY_VERSION: 'unlogged_smart_and_login_web_v1',
          }),
          credentials: 'include',
        });
        return await resp.json();
      }, { token: apiToken, email: email2, password, username });
      
      log(`Retry: ${JSON.stringify(createResult2).substring(0, 500)}`);
      
      if (createResult2.results?.arl) {
        const arl = createResult2.results.arl;
        log(`\n========== ARL: ${arl} ==========`);
        fs.writeFileSync('/tmp/deezer-register/result.json', JSON.stringify({
          email: email2, password, username, arl, timestamp: new Date().toISOString()
        }, null, 2));
      }
    } else {
      log(`Error: ${JSON.stringify(createResult.error)}`);
    }

  } catch (err) {
    log(`ERROR: ${err.message}`);
  } finally {
    await browser.close();
  }
}

main().catch(console.error);
