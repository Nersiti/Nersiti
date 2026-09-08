# -*- coding: utf-8 -*-
"""Небольшой движок трассировки лучей по CSG-модели.

Тело задаётся как объединение выпуклых частей минус объединение вычитаемых
выпуклых частей. Каждая выпуклая часть — пересечение ограничений трёх типов:

    Cyl(cx, cy, r)   цилиндр вдоль оси Z
    Cone(k, b)       конус r <= k*z + b (фаски 45°, k = ±1)
    Plane(n, d)      полупространство n·p <= d

Пересечения считаются аналитически, поэтому кромки и фаски получаются
точными, без триангуляции.
"""

from __future__ import annotations

import numpy as np

TOL = 1e-3
INF = 1e9


def _norm(v):
    v = np.asarray(v, dtype=np.float64)
    return v / np.linalg.norm(v)


class Cyl:
    def __init__(self, cx, cy, r):
        self.cx, self.cy, self.r = cx, cy, r

    def inside(self, p, eps):
        return np.hypot(p[:, 0] - self.cx, p[:, 1] - self.cy) < self.r + eps

    def hits(self, o, d):
        ox, oy = o[:, 0] - self.cx, o[:, 1] - self.cy
        dx, dy = d[:, 0], d[:, 1]
        a = dx * dx + dy * dy
        b = 2.0 * (ox * dx + oy * dy)
        c = ox * ox + oy * oy - self.r * self.r
        par = a < 1e-12
        a_s = np.where(par, 1.0, a)
        disc = b * b - 4.0 * a_s * c
        sq = np.sqrt(np.maximum(disc, 0.0))
        ok = ~par & (disc > 0.0)
        return [(np.where(ok, (-b - sq) / (2 * a_s), INF), ok),
                (np.where(ok, (-b + sq) / (2 * a_s), INF), ok)]

    def normal(self, p):
        n = np.zeros_like(p)
        n[:, 0] = (p[:, 0] - self.cx) / self.r
        n[:, 1] = (p[:, 1] - self.cy) / self.r
        return n


class Cone:
    """Поверхность r = k*z + b; внутренность — r <= k*z + b."""

    def __init__(self, k, b):
        self.k, self.b = float(k), float(b)

    def _u(self, z):
        return self.k * z + self.b

    def inside(self, p, eps):
        return np.hypot(p[:, 0], p[:, 1]) < self._u(p[:, 2]) + eps

    def hits(self, o, d):
        u0 = self._u(o[:, 2])
        ud = self.k * d[:, 2]
        a = d[:, 0] ** 2 + d[:, 1] ** 2 - ud * ud
        b = 2.0 * (o[:, 0] * d[:, 0] + o[:, 1] * d[:, 1] - u0 * ud)
        c = o[:, 0] ** 2 + o[:, 1] ** 2 - u0 * u0
        lin = np.abs(a) < 1e-12
        a_s = np.where(lin, 1.0, a)
        disc = b * b - 4.0 * a_s * c
        sq = np.sqrt(np.maximum(disc, 0.0))
        b_s = np.where(np.abs(b) < 1e-12, 1.0, b)
        t_lin = np.where(np.abs(b) < 1e-12, INF, -c / b_s)
        t0 = np.where(lin, t_lin, (-b - sq) / (2 * a_s))
        t1 = np.where(lin, INF, (-b + sq) / (2 * a_s))
        ok = np.where(lin, np.abs(b) >= 1e-12, disc > 0.0)
        return [(np.where(ok, t0, INF), ok), (np.where(ok, t1, INF), ok)]

    def normal(self, p):
        u = self._u(p[:, 2])
        n = np.stack([p[:, 0], p[:, 1], -self.k * u], axis=1)
        ln = np.linalg.norm(n, axis=1)
        return n / np.where(ln[:, None] < 1e-9, 1.0, ln[:, None])


class Plane:
    """Полупространство n·p <= d."""

    def __init__(self, n, d):
        self.n = _norm(n)
        self.d = float(d)

    def inside(self, p, eps):
        return p @ self.n < self.d + eps

    def hits(self, o, d):
        den = d @ self.n
        flat = np.abs(den) < 1e-12
        t = (self.d - o @ self.n) / np.where(flat, 1.0, den)
        return [(np.where(flat, INF, t), ~flat)]

    def normal(self, p):
        return np.repeat(self.n[None, :], p.shape[0], axis=0)


def slab(axis, lo, hi):
    n_lo = np.zeros(3); n_lo[axis] = -1.0
    n_hi = np.zeros(3); n_hi[axis] = 1.0
    return [Plane(n_lo, -lo), Plane(n_hi, hi)]


class Piece:
    """Выпуклая часть — пересечение ограничений."""

    def __init__(self, *constraints):
        self.cs = []
        for c in constraints:
            self.cs.extend(c if isinstance(c, (list, tuple)) else [c])

    def inside(self, p, eps=TOL):
        acc = np.ones(p.shape[0], dtype=bool)
        for c in self.cs:
            acc &= c.inside(p, eps)
        return acc

    def candidates(self, o, d):
        for c in self.cs:
            for t, ok in c.hits(o, d):
                yield t, ok, c


class Solid:
    def __init__(self, adds, subs=()):
        self.adds, self.subs = list(adds), list(subs)

    def inside_any_add(self, p, eps=TOL):
        acc = np.zeros(p.shape[0], dtype=bool)
        for a in self.adds:
            acc |= a.inside(p, eps)
        return acc

    def inside_any_sub(self, p, skip=None, eps=-TOL):
        acc = np.zeros(p.shape[0], dtype=bool)
        for i, s in enumerate(self.subs):
            if i != skip:
                acc |= s.inside(p, eps)
        return acc

    def trace(self, o, d):
        """Ближайшее пересечение: (t, нормаль, попадание, это_срез)."""
        ts, ns, cut_flags = [], [], []

        def push(t, ok, normal, is_cut):
            ts.append(np.where(ok, t, INF))
            ns.append(normal)
            cut_flags.append(is_cut)

        for i, piece in enumerate(self.adds):
            for t, ok, c in piece.candidates(o, d):
                p = o + np.where(np.abs(t) < INF / 2, t, 0.0)[:, None] * d
                other = np.zeros(o.shape[0], dtype=bool)
                for j, q in enumerate(self.adds):
                    if j != i:
                        other |= q.inside(p, -TOL)
                good = (ok & (t > TOL) & piece.inside(p) & ~other
                        & ~self.inside_any_sub(p))
                push(t, good, c.normal(p), False)

        for i, piece in enumerate(self.subs):
            for t, ok, c in piece.candidates(o, d):
                p = o + np.where(np.abs(t) < INF / 2, t, 0.0)[:, None] * d
                good = (ok & (t > TOL) & piece.inside(p) & self.inside_any_add(p)
                        & ~self.inside_any_sub(p, skip=i))
                push(t, good, -c.normal(p), getattr(piece, "is_cut", False))

        stack = np.stack(ts)
        best = np.argmin(stack, axis=0)
        t_best = np.take_along_axis(stack, best[None, :], axis=0)[0]
        n_best = np.take_along_axis(np.stack(ns), best[None, :, None], axis=0)[0]
        return t_best, n_best, t_best < INF / 2, np.array(cut_flags)[best]
