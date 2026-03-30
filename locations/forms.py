from django import forms


class FilmSearchForm(forms.Form):
    query = forms.CharField(
        label="Titre du film",
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ex: Inception, The Dark Knight...',
        })
    )
    wikidata_id = forms.CharField(
        label="Identifiant Wikidata du film",
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ex: Q25188',
        })
    )


class ActorSearchForm(forms.Form):
    actor_name = forms.CharField(
        label="Nom de l'acteur",
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ex: Leonardo DiCaprio, Marion Cotillard...',
        })
    )


class LocationSearchForm(forms.Form):
    location_name = forms.CharField(
        label="Nom du lieu",
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ex: Paris, New York, Londres...',
        })
    )


class ActorImportForm(forms.Form):
    wikidata_id = forms.CharField(
        label="Identifiant Wikidata de l'acteur",
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ex: Q37175 (Leonardo DiCaprio)',
        }),
        help_text="Entrez l'identifiant Wikidata de l'acteur (format : Q suivi de chiffres)"
    )

    def clean_wikidata_id(self):
        value = self.cleaned_data['wikidata_id'].strip().upper()
        if not value.startswith('Q'):
            raise forms.ValidationError("L'identifiant Wikidata doit commencer par 'Q' (ex: Q37175)")
        if not value[1:].isdigit():
            raise forms.ValidationError("L'identifiant Wikidata doit être au format Q suivi de chiffres")
        return value


class AdminImportForm(forms.Form):
    wikidata_id = forms.CharField(
        label="Identifiant Wikidata du film",
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ex: Q25188 (Inception)',
        }),
        help_text="Entrez l'identifiant Wikidata du film à importer (format: Q suivi de chiffres)"
    )

    def clean_wikidata_id(self):
        value = self.cleaned_data['wikidata_id'].strip().upper()
        if not value.startswith('Q'):
            raise forms.ValidationError("L'identifiant Wikidata doit commencer par 'Q' (ex: Q25188)")
        if not value[1:].isdigit():
            raise forms.ValidationError("L'identifiant Wikidata doit être au format Q suivi de chiffres (ex: Q25188)")
        return value
