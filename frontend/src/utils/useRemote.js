import { useCallback, useEffect, useState } from "react";
import { apiError } from "./api";

export default function useRemote(loader, dependencies = []) {
  const [state, setState] = useState({ data: null, loading: true, error: "" });
  const [revision, setRevision] = useState(0);
  const reload = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    let active = true;
    setState((previous) => ({ ...previous, loading: true, error: "" }));
    Promise.resolve().then(loader).then((data) => { if (active) setState({ data, loading: false, error: "" }); })
      .catch((error) => { if (active) setState((previous) => ({ ...previous, loading: false, error: apiError(error) })); });
    return () => { active = false; };
  }, [...dependencies, revision]);
  return { ...state, reload };
}
