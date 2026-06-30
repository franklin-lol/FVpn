import { create } from "zustand";
import { persist } from "zustand/middleware";
import api from "../utils/api";

export const useAuthStore = create(
  persist(
    (set, get) => ({
      token:   null,
      user:    null,
      isAdmin: false,

      login: async (username, password) => {
        const form = new URLSearchParams({ username, password });
        const { data } = await api.post("/api/auth/login", form, {
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
        });
        set({ token: data.access_token, user: data.username, isAdmin: data.is_admin });
        api.defaults.headers.common["Authorization"] = `Bearer ${data.access_token}`;
        return data;
      },

      logout: () => {
        set({ token: null, user: null, isAdmin: false });
        delete api.defaults.headers.common["Authorization"];
      },

      hydrate: () => {
        const { token } = get();
        if (token) api.defaults.headers.common["Authorization"] = `Bearer ${token}`;
      },
    }),
    { name: "fvpn-auth", partialize: (s) => ({ token: s.token, user: s.user, isAdmin: s.isAdmin }) }
  )
);

export const useStatsStore = create((set) => ({
  live: null,
  setLive: (data) => set({ live: data }),
}));
