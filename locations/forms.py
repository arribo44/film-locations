from django import forms
from django.utils.translation import gettext_lazy as _


class FilmSearchForm(forms.Form):
    query = forms.CharField(
        label=_("Titre du film"),
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Ex : Inception, The Dark Knight...'),
        })
    )
    wikidata_id = forms.CharField(
        label=_("Identifiant Wikidata du film"),
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Ex : Q25188'),
        })
    )


class ActorSearchForm(forms.Form):
    actor_name = forms.CharField(
        label=_("Nom de l'acteur"),
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Ex : Leonardo DiCaprio, Marion Cotillard...'),
        })
    )


class LocationSearchForm(forms.Form):
    location_name = forms.CharField(
        label=_("Nom du lieu"),
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Ex : Paris, New York, Londres...'),
        })
    )


class ActorImportForm(forms.Form):
    wikidata_id = forms.CharField(
        label=_("Identifiant Wikidata de l'acteur"),
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Ex : Q38111 (Leonardo DiCaprio)'),
        }),
        help_text=_("Entrez l'identifiant Wikidata de l'acteur (format : Q suivi de chiffres)")
    )

    def clean_wikidata_id(self):
        value = self.cleaned_data['wikidata_id'].strip().upper()
        if not value.startswith('Q'):
            raise forms.ValidationError(_("L'identifiant Wikidata doit commencer par 'Q' (ex: Q38111)"))
        if not value[1:].isdigit():
            raise forms.ValidationError(_("L'identifiant Wikidata doit être au format Q suivi de chiffres"))
        return value


class AdminImportForm(forms.Form):
    wikidata_id = forms.CharField(
        label=_("Identifiant Wikidata du film"),
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Ex : Q25188 (Inception)'),
        }),
        help_text=_("Entrez l'identifiant Wikidata du film à importer (format: Q suivi de chiffres)")
    )

    def clean_wikidata_id(self):
        value = self.cleaned_data['wikidata_id'].strip().upper()
        if not value.startswith('Q'):
            raise forms.ValidationError(_("L'identifiant Wikidata doit commencer par 'Q' (ex: Q25188)"))
        if not value[1:].isdigit():
            raise forms.ValidationError(_("L'identifiant Wikidata doit être au format Q suivi de chiffres (ex: Q25188)"))
        return value
