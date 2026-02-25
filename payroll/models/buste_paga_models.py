"""
buste_paga_models.py

Modelli per la gestione delle buste paga importate da PDF.
Schema personalizzato adattato al formato cedolini aziendali.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from employee.models import Employee


class BustaPaga(models.Model):
    """
    Intestazione della busta paga.
    id_busta è la chiave primaria testuale (es. "10322000078GEN.2026").
    """

    id_busta = models.CharField(
        max_length=50,
        primary_key=True,
        verbose_name=_("ID Busta"),
        help_text=_('Identificativo univoco busta, es. "10322000078GEN.2026"'),
    )
    matricola = models.CharField(
        max_length=50,
        verbose_name=_("Matricola"),
    )
    # Collegamento opzionale al dipendente Horilla tramite codice_paghe
    employee_id = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="buste_paga",
        verbose_name=_("Dipendente"),
        help_text=_("Collegato automaticamente tramite matricola == employee.codice_paghe"),
    )
    filiale = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name=_("Filiale"),
    )
    mese = models.CharField(
        max_length=3,
        verbose_name=_("Mese"),
        help_text=_('Es. "GEN", "FEB", "MAR"'),
    )
    anno = models.IntegerField(
        verbose_name=_("Anno"),
    )
    netto = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Netto"),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("matricola", "mese", "anno")]
        verbose_name = _("Busta Paga")
        verbose_name_plural = _("Buste Paga")
        ordering = ["-anno", "mese", "matricola"]

    def __str__(self):
        return f"{self.id_busta} — {self.matricola} {self.mese}/{self.anno}"


class SezioneAC(models.Model):
    """
    Sezione ferie / f.s. / ROL della busta paga (campi fissi).
    Relazione 1:1 con BustaPaga.
    """

    id_busta = models.OneToOneField(
        BustaPaga,
        on_delete=models.CASCADE,
        primary_key=True,
        db_column="id_busta",
        related_name="sezione_ac",
        verbose_name=_("Busta Paga"),
    )
    # Ferie
    ferie_residuo_ap = models.FloatField(null=True, blank=True, verbose_name=_("Ferie Residuo AP"))
    ferie_maturazione_ac = models.FloatField(null=True, blank=True, verbose_name=_("Ferie Maturazione AC"))
    ferie_godute_ac = models.FloatField(null=True, blank=True, verbose_name=_("Ferie Godute AC"))
    ferie_residuo = models.FloatField(null=True, blank=True, verbose_name=_("Ferie Residuo"))
    # Festività soppresse (f.s.)
    fs_residuo_ap = models.FloatField(null=True, blank=True, verbose_name=_("F.S. Residuo AP"))
    fs_maturazione_ac = models.FloatField(null=True, blank=True, verbose_name=_("F.S. Maturazione AC"))
    fs_godute_ac = models.FloatField(null=True, blank=True, verbose_name=_("F.S. Godute AC"))
    fs_residuo = models.FloatField(null=True, blank=True, verbose_name=_("F.S. Residuo"))
    # ROL
    rol_residuo_ap = models.FloatField(null=True, blank=True, verbose_name=_("ROL Residuo AP"))
    rol_maturazione_ac = models.FloatField(null=True, blank=True, verbose_name=_("ROL Maturazione AC"))
    rol_godute_ac = models.FloatField(null=True, blank=True, verbose_name=_("ROL Godute AC"))
    rol_residuo = models.FloatField(null=True, blank=True, verbose_name=_("ROL Residuo"))

    class Meta:
        verbose_name = _("Sezione AC")
        verbose_name_plural = _("Sezioni AC")

    def __str__(self):
        return f"SezioneAC — {self.id_busta_id}"


class Causale(models.Model):
    """
    Una riga per tipo causale per busta (es. RETRIB.MES, FERIE, R.O.L.).
    """

    id_busta = models.ForeignKey(
        BustaPaga,
        on_delete=models.CASCADE,
        db_column="id_busta",
        related_name="causali",
        verbose_name=_("Busta Paga"),
    )
    causale = models.CharField(
        max_length=100,
        verbose_name=_("Causale"),
        help_text=_('Es. "RETRIB.MES", "FERIE", "R.O.L."'),
    )
    ore_totali = models.FloatField(null=True, blank=True, verbose_name=_("Ore Totali"))
    gg_totali = models.FloatField(null=True, blank=True, verbose_name=_("Giorni Totali"))

    class Meta:
        verbose_name = _("Causale")
        verbose_name_plural = _("Causali")
        ordering = ["id"]

    def __str__(self):
        return f"{self.causale} [{self.id_busta_id}]"


class CausaleGiorno(models.Model):
    """
    Dettaglio ore per singolo giorno di una causale (solo giorni con ore != 0).
    """

    id_busta = models.ForeignKey(
        BustaPaga,
        on_delete=models.CASCADE,
        db_column="id_busta",
        related_name="causali_giorni",
        verbose_name=_("Busta Paga"),
    )

    id_causale = models.ForeignKey(
        Causale,
        on_delete=models.CASCADE,
        db_column="id_causale",
        related_name="giorni",
        verbose_name=_("Causale"),
    )
    giorno = models.IntegerField(
        verbose_name=_("Giorno"),
        help_text=_("Numero del giorno del mese (1..31)"),
    )
    ore = models.FloatField(verbose_name=_("Ore"))

    class Meta:
        verbose_name = _("Causale Giorno")
        verbose_name_plural = _("Causali Giorni")
        unique_together = [("id_causale", "giorno")]
        ordering = ["giorno"]

    def __str__(self):
        return f"Giorno {self.giorno}: {self.ore}h [{self.id_causale}]"


class VoceBusta(models.Model):
    """
    Voci della busta paga (sezione_voci — variabile, una riga per voce).
    """

    id_busta = models.ForeignKey(
        BustaPaga,
        on_delete=models.CASCADE,
        db_column="id_busta",
        related_name="voci",
        verbose_name=_("Busta Paga"),
    )
    codice_voce = models.IntegerField(
        verbose_name=_("Codice Voce"),
        help_text=_("Es. 300, 1001, 1445"),
    )
    descrizione = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name=_("Descrizione"),
    )
    aliquota = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Aliquota (ALIQ)"),
    )
    unita = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Unità (UNIT)"),
    )
    val = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Valore Unitario (VAL)"),
    )
    competenza = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Competenza (COMP)"),
    )
    trattenuta = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Trattenuta (TRAT)"),
    )

    class Meta:
        verbose_name = _("Voce Busta")
        verbose_name_plural = _("Voci Busta")
        ordering = ["codice_voce"]

    def __str__(self):
        return f"{self.codice_voce} — {self.descrizione} [{self.id_busta_id}]"
