"""Qualified English/French semantic aliases for TikTok UI controls.

The automation does not infer a device language and does not translate at run
time. It matches a small reviewed alias set against fresh native hierarchy
evidence, preserving strict semantic selection and avoiding guessed coordinates.
"""
from __future__ import annotations


FOR_YOU = ("For You", "For you", "Pour toi")
FOLLOWING = ("Following", "Abonnements")
SEARCH = ("Search", "Rechercher")

COMMENTS = ("Comments", "Comment", "Commentaires", "Commentaire")
ADD_COMMENT = ("Add comment", "Add comment...", "Ajouter un commentaire")

PROFILE_FOLLOWERS = ("Followers", "Abonnés")
PROFILE_FOLLOWING = ("Following", "Abonnements")
PROFILE_LIKES = ("Likes", "J'aime")
PROFILE_VIDEOS = ("Videos", "Vidéos")

HASHTAG_TABS = ("Hashtags", "Hashtag")
ACCOUNT_TABS = ("Users", "Accounts", "User", "Utilisateurs", "Comptes", "Utilisateur")

FOLLOWING_TRENDING_CREATORS = ("Trending creators", "Créateurs tendance")
FOLLOWING_PREREQUISITE = (
    "Follow an account to see their latest videos here",
    "Follow an account to see their latest videos here.",
    "Suivez un compte",
)

LOADING_TERMS = (
    "loading",
    "please wait",
    "retry",
    "no internet connection",
    "network error",
    "chargement",
    "veuillez patienter",
    "réessayer",
    "pas de connexion internet",
    "aucune connexion internet",
    "erreur réseau",
)

FYP_VARIANT_PHRASES = {
    "live-card": (
        "tap to watch live",
        "watch live",
        "live now",
        "appuyez pour regarder le live",
        "regarder le live",
        "live maintenant",
    ),
    "repost-affordance": (
        "repost to followers",
        "reposted",
        "republier auprès des abonnés",
        "republié",
    ),
    "photo-card": (
        "photo mode",
        "swipe left",
        "swipe to see more",
        "view photos",
        "mode photo",
        "balayez vers la gauche",
        "balayez pour en voir plus",
        "voir les photos",
    ),
    "sponsored-card": (
        "sponsored",
        "advertisement",
        "paid partnership",
        "promoted",
        "sponsorisé",
        "publicité",
        "partenariat rémunéré",
        "promu",
    ),
    "shop-card": (
        "shop now",
        "view product",
        "product details",
        "buy now",
        "acheter maintenant",
        "voir le produit",
        "détails du produit",
    ),
}
