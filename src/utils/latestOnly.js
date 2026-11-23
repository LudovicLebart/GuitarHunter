/** Lecture « la plus récente gagne » : une réponse plus lente qu'une lecture lancée après elle, ou arrivée après `close()`,
 *  est ignorée (ni `emit` ni `fail`). */
export const latestOnly = (load, emit, fail) => {
  let seq = 0;
  let closed = false;
  const run = async () => {
    const mine = ++seq;
    try {
      const result = await load();
      if (!closed && mine === seq) emit(result);
    } catch (error) {
      if (!closed && mine === seq) fail(error);
    }
  };
  run.close = () => { closed = true; };
  return run;
};
