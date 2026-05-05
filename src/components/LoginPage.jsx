import React, { useState } from 'react';
import { useAuthContext } from '../context/AuthContext';
import { Guitar, Lock, Mail, AlertCircle, Loader2, ArrowLeft } from 'lucide-react';

const LoginPage = () => {
  const { signIn, signUp, resetPassword } = useAuthContext();
  const [mode, setMode] = useState('login'); // 'login', 'signup', 'reset'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setLoading(true);

    try {
      if (mode === 'login') {
        await signIn(email, password);
      } else if (mode === 'signup') {
        await signUp(email, password);
      } else if (mode === 'reset') {
        await resetPassword(email);
        setSuccess('Un email de réinitialisation a été envoyé à votre adresse.');
      }
    } catch (err) {
      const messages = {
        'auth/invalid-credential': 'Email ou mot de passe incorrect.',
        'auth/invalid-email': 'Adresse email invalide.',
        'auth/user-disabled': 'Ce compte a été désactivé.',
        'auth/too-many-requests': 'Trop de tentatives. Réessayez plus tard.',
        'auth/email-already-in-use': 'Cette adresse email est déjà utilisée.',
        'auth/weak-password': 'Le mot de passe doit contenir au moins 6 caractères.',
        'auth/user-not-found': 'Aucun compte trouvé avec cet email.',
      };
      setError(messages[err.code] || 'Erreur d\'authentification. Vérifiez vos informations.');
    } finally {
      setLoading(false);
    }
  };

  const toggleMode = (newMode) => {
    setMode(newMode);
    setError('');
    setSuccess('');
  };

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
      {/* Background glow */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-blue-600/10 rounded-full blur-3xl animate-pulse" />
      </div>

      <div className="relative w-full max-w-md">
        {/* Logo / Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-blue-600/20 border border-blue-500/30 rounded-2xl mb-4 shadow-lg shadow-blue-900/20">
            <Guitar className="text-blue-400" size={32} />
          </div>
          <h1 className="text-3xl font-black text-white tracking-tight">Guitar Hunter</h1>
          <p className="text-slate-400 text-sm mt-1">
            {mode === 'login' && 'Connectez-vous à votre espace personnel'}
            {mode === 'signup' && 'Créez votre compte personnel'}
            {mode === 'reset' && 'Réinitialisez votre mot de passe'}
          </p>
        </div>

        {/* Card */}
        <div className="bg-slate-900/80 backdrop-blur border border-slate-700/50 rounded-2xl p-8 shadow-2xl shadow-black/50">
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Email */}
            <div>
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2 block">
                Adresse Email
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={16} />
                <input
                  type="email"
                  name="email"
                  autoComplete="username"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="votre@email.com"
                  required
                  className="w-full bg-slate-800 border border-slate-700 text-white placeholder-slate-500 rounded-xl pl-10 pr-4 py-3 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
                />
              </div>
            </div>

            {/* Password (only if not reset mode) */}
            {mode !== 'reset' && (
              <div>
                <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2 block">
                  Mot de Passe
                </label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={16} />
                  <input
                    type="password"
                    name="password"
                    autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    required
                    className="w-full bg-slate-800 border border-slate-700 text-white placeholder-slate-500 rounded-xl pl-10 pr-4 py-3 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
                  />
                </div>
                {mode === 'login' && (
                  <button
                    type="button"
                    onClick={() => toggleMode('reset')}
                    className="text-xs text-blue-400 hover:text-blue-300 mt-2 font-medium"
                  >
                    Mot de passe oublié ?
                  </button>
                )}
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="flex items-center gap-3 bg-rose-500/10 border border-rose-500/30 text-rose-400 rounded-xl px-4 py-3 text-sm animate-in fade-in slide-in-from-top-1">
                <AlertCircle size={16} className="flex-shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {/* Success */}
            {success && (
              <div className="flex items-center gap-3 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 rounded-xl px-4 py-3 text-sm animate-in fade-in slide-in-from-top-1">
                <div className="w-4 h-4 rounded-full bg-emerald-500/20 flex items-center justify-center">
                  <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                </div>
                <span>{success}</span>
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold rounded-xl py-3 px-4 transition-colors flex items-center justify-center gap-2 mt-4 shadow-lg shadow-blue-600/20"
            >
              {loading ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  {mode === 'login' && 'Connexion...'}
                  {mode === 'signup' && 'Création...'}
                  {mode === 'reset' && 'Envoi...'}
                </>
              ) : (
                <>
                  {mode === 'login' && 'Se connecter'}
                  {mode === 'signup' && 'Créer un compte'}
                  {mode === 'reset' && 'Envoyer le lien'}
                </>
              )}
            </button>

            {/* Switch Mode */}
            <div className="pt-4 text-center">
              {mode === 'login' ? (
                <p className="text-slate-400 text-sm">
                  Pas encore de compte ?{' '}
                  <button
                    type="button"
                    onClick={() => toggleMode('signup')}
                    className="text-blue-400 hover:text-blue-300 font-bold"
                  >
                    S'inscrire
                  </button>
                </p>
              ) : (
                <button
                  type="button"
                  onClick={() => toggleMode('login')}
                  className="inline-flex items-center gap-2 text-slate-400 hover:text-white text-sm font-medium transition-colors"
                >
                  <ArrowLeft size={14} />
                  Retour à la connexion
                </button>
              )}
            </div>
          </form>
        </div>

        <p className="text-center text-slate-600 text-xs mt-6 font-bold">
          Guitar Hunter AI © 2026
        </p>
      </div>
    </div>
  );
};

export default LoginPage;
