import axios, {
  AxiosError,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from 'axios';

/** Без завершающего слэша — чтобы не получать `/api//token/` при сборке URL */
const API_ROOT = 'http://127.0.0.1:8000/api';
const API_BASE_URL = `${API_ROOT}/`;

const ACCESS_TOKEN_KEY = 'shophelper.accessToken';
const REFRESH_TOKEN_KEY = 'shophelper.refreshToken';

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setTokens(accessToken: string, refreshToken: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

type TokenPairResponse = { access: string; refresh: string };

const refreshClient = axios.create({ baseURL: API_BASE_URL });

async function refreshAccessToken(): Promise<string> {
  const refresh = getRefreshToken();
  if (!refresh) {
    throw new Error('No refresh token');
  }
  const resp = await refreshClient.post<{ access: string }>('/token/refresh/', { refresh });
  const nextAccess = resp.data.access;
  const currentRefresh = refresh;
  setTokens(nextAccess, currentRefresh);
  return nextAccess;
}

function withAuthHeader(
  config: InternalAxiosRequestConfig,
  accessToken: string,
): InternalAxiosRequestConfig {
  config.headers = config.headers ?? {};
  config.headers.Authorization = `Bearer ${accessToken}`;
  return config;
}

type RetriableRequestConfig = InternalAxiosRequestConfig & { _retry?: boolean };

function setupInterceptors(instance: AxiosInstance): void {
  instance.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    const token = getAccessToken();
    if (!token) {
      return config;
    }
    return withAuthHeader(config, token);
  });

  let isRefreshing = false;
  let pending: Array<(token: string) => void> = [];

  instance.interceptors.response.use(
    (response) => response,
    async (error: AxiosError) => {
      const original = (error.config ?? ({} as InternalAxiosRequestConfig)) as RetriableRequestConfig;
      const status = error.response?.status;

      if (status !== 401 || original._retry) {
        return Promise.reject(error);
      }

      const refresh = getRefreshToken();
      if (!refresh) {
        clearTokens();
        return Promise.reject(error);
      }

      original._retry = true;

      if (isRefreshing) {
        return new Promise((resolve) => {
          pending.push((token: string) => {
            resolve(instance(withAuthHeader(original, token)));
          });
        });
      }

      isRefreshing = true;
      try {
        const newToken = await refreshAccessToken();
        pending.forEach((cb) => cb(newToken));
        pending = [];
        return instance(withAuthHeader(original, newToken));
      } catch (refreshErr) {
        pending = [];
        clearTokens();
        return Promise.reject(refreshErr);
      } finally {
        isRefreshing = false;
      }
    },
  );
}

export const api = axios.create({
  baseURL: API_BASE_URL,
});

setupInterceptors(api);

export async function loginRequest(username: string, password: string): Promise<TokenPairResponse> {
  const resp = await axios.post<TokenPairResponse>(`${API_ROOT}/token/`, { username, password });
  return resp.data;
}

export default api;
