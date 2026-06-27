import axios from "axios";

const api = axios.create({
  baseURL: "",
  timeout: 30000,
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("uniproxy-auth");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export default api;

// Convenience wrappers
export const nodesApi = {
  list:      ()         => api.get("/api/nodes"),
  create:    (d)        => api.post("/api/nodes", d),
  delete:    (id)       => api.delete(`/api/nodes/${id}`),
  check:     (id)       => api.post(`/api/nodes/${id}/check`),
  checkAll:  ()         => api.post("/api/nodes/check-all"),
  autoSetup: (id, data) => api.post(`/api/nodes/${id}/auto-setup`, data),
};

export const usersApi = {
  list:         (skip=0, limit=100) => api.get(`/api/users?skip=${skip}&limit=${limit}`),
  create:       (d)   => api.post("/api/users", d),
  update:       (id,d) => api.patch(`/api/users/${id}`, d),
  delete:       (id)  => api.delete(`/api/users/${id}`),
  resetTraffic: (id)  => api.post(`/api/users/${id}/reset-traffic`),
};

export const protocolsApi = {
  list:      (nodeId) => api.get(`/api/protocols${nodeId ? `?node_id=${nodeId}` : ""}`),
  create:    (d)      => api.post("/api/protocols", d),
  delete:    (id)     => api.delete(`/api/protocols/${id}`),
  preview:   (d)      => api.post("/api/protocols/preview", d),
  supported: ()       => api.get("/api/protocols/supported"),
};

export const subsApi = {
  list:   ()      => api.get("/api/subscriptions"),
  create: (d)     => api.post("/api/subscriptions", d),
  delete: (id)    => api.delete(`/api/subscriptions/${id}`),
  qrUrl:  (token) => `/api/subscriptions/qr/${token}`,
};

export const statsApi = {
  dashboard: () => api.get("/api/stats/dashboard"),
  system:    () => api.get("/api/stats/system"),
  nodeHistory:(id, days=7) => api.get(`/api/stats/nodes/${id}/history?days=${days}`),
};
