"""JavaScript executed inside Chrome for bounded product API fetching."""

BOUNDED_FETCH_SCRIPT = """
const ids = arguments[0];
const concurrency = arguments[1];
const requestTimeoutMs = arguments[2];
const done = arguments[arguments.length - 1];
const results = new Array(ids.length);
let nextIndex = 0;
let challengeSeen = false;

function skippedAfterChallenge(productId) {
  const timestamp = new Date().toISOString();
  return {
    productId, status: null, contentType: '', body: '',
    error: 'not requested after another request received a challenge',
    startedAt: timestamp, endedAt: timestamp, elapsedSeconds: 0,
  };
}

async function fetchProduct(productId) {
  const startedAt = new Date().toISOString();
  const started = performance.now();
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), requestTimeoutMs);
  try {
    const response = await fetch(
      `https://api.tiki.vn/product-detail/api/v1/products/${productId}`,
      {
        method: 'GET', credentials: 'include', signal: controller.signal,
        headers: { 'Accept': 'application/json, text/plain, */*' },
      },
    );
    const body = await response.text();
    const contentType = response.headers.get('content-type') || '';
    const isNotFound = response.status === 404 || response.status === 410;
    const isJson = contentType.toLowerCase().includes('json');
    return {
      productId, status: response.status, contentType, body, error: null,
      challenge: !isNotFound && (response.status !== 200 || !isJson),
      startedAt, endedAt: new Date().toISOString(),
      elapsedSeconds: (performance.now() - started) / 1000,
    };
  } catch (error) {
    return {
      productId, status: null, contentType: '', body: '',
      error: error.name === 'AbortError' ? 'timeout' : String(error),
      startedAt, endedAt: new Date().toISOString(),
      elapsedSeconds: (performance.now() - started) / 1000,
    };
  } finally {
    clearTimeout(timeoutId);
  }
}

async function worker() {
  while (true) {
    if (challengeSeen) return;
    const index = nextIndex++;
    if (index >= ids.length) return;
    const result = await fetchProduct(ids[index]);
    results[index] = result;
    if (result.challenge) challengeSeen = true;
  }
}

Promise.all(Array.from({ length: Math.min(concurrency, ids.length) }, worker))
  .then(() => {
    // A challenge stops new requests, but every caller ID still needs an
    // explicit resumable result instead of a sparse-array hole.
    for (let index = 0; index < ids.length; index += 1) {
      if (results[index] === undefined) {
        results[index] = skippedAfterChallenge(ids[index]);
      }
    }
    done(results);
  })
  .catch((error) => done({ error: String(error) }));
"""
