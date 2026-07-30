export const FALLBACK_MAP = {
  "_comment": "SINGLE SOURCE OF TRUTH for Bangla Braille character mappings.",
  "_warning": "11 of 50 letters verified from braille_img/. Letters with verified=false still carry Bharati PLACEHOLDER patterns -- supply images for them and re-run tools/import_braille_images.py.",
  "standard": "PLACEHOLDER_BHARATI",
  "verified": false,
  "dot_layout": {
    "_comment": "Braille cell dot numbering. Column-major, the international standard.",
    "1": "top-left",
    "2": "middle-left",
    "3": "bottom-left",
    "4": "top-right",
    "5": "middle-right",
    "6": "bottom-right"
  },
  "letters": [
    {
      "id": 0,
      "char": "অ",
      "name": "a",
      "roman": "o",
      "category": "vowel",
      "dots": [
        1
      ],
      "audio": "0001.mp3",
      "verified": true,
      "source": "braille_img/ao.webp"
    },
    {
      "id": 1,
      "char": "আ",
      "name": "aa",
      "roman": "a",
      "category": "vowel",
      "dots": [
        3,
        4,
        5
      ],
      "audio": "0002.mp3",
      "verified": true,
      "source": "braille_img/aa.webp"
    },
    {
      "id": 2,
      "char": "ই",
      "name": "i",
      "roman": "i",
      "category": "vowel",
      "dots": [
        2,
        4
      ],
      "audio": "0003.mp3",
      "verified": true,
      "source": "braille_img/ei.webp"
    },
    {
      "id": 3,
      "char": "ঈ",
      "name": "ii",
      "roman": "ee",
      "category": "vowel",
      "dots": [
        3,
        5
      ],
      "audio": "0004.mp3",
      "verified": true,
      "source": "braille_img/eiii.webp"
    },
    {
      "id": 4,
      "char": "উ",
      "name": "u",
      "roman": "u",
      "category": "vowel",
      "dots": [
        1,
        3,
        6
      ],
      "audio": "0005.mp3",
      "verified": true,
      "source": "braille_img/uu.webp"
    },
    {
      "id": 5,
      "char": "ঊ",
      "name": "uu",
      "roman": "oo",
      "category": "vowel",
      "dots": [
        1,
        2,
        5,
        6
      ],
      "audio": "0006.mp3",
      "verified": true,
      "source": "braille_img/uuuu.webp"
    },
    {
      "id": 6,
      "char": "ঋ",
      "name": "ri",
      "roman": "ri",
      "category": "vowel",
      "dots": [
        1,
        2,
        3,
        5
      ],
      "audio": "0007.mp3",
      "verified": true,
      "source": "braille_img/ri.webp"
    },
    {
      "id": 7,
      "char": "এ",
      "name": "e",
      "roman": "e",
      "category": "vowel",
      "dots": [
        1,
        5
      ],
      "audio": "0008.mp3",
      "verified": true,
      "source": "braille_img/e.webp"
    },
    {
      "id": 8,
      "char": "ঐ",
      "name": "oi",
      "roman": "oi",
      "category": "vowel",
      "dots": [
        3,
        4
      ],
      "audio": "0009.mp3",
      "verified": true,
      "source": "braille_img/oi.webp"
    },
    {
      "id": 9,
      "char": "ও",
      "name": "o",
      "roman": "o",
      "category": "vowel",
      "dots": [
        1,
        3,
        5
      ],
      "audio": "0010.mp3",
      "verified": true,
      "source": "braille_img/o.webp"
    },
    {
      "id": 10,
      "char": "ঔ",
      "name": "ou",
      "roman": "ou",
      "category": "vowel",
      "dots": [
        2,
        4,
        6
      ],
      "audio": "0011.mp3",
      "verified": true,
      "source": "braille_img/ou.webp"
    },
    {
      "id": 11,
      "char": "ক",
      "name": "ka",
      "roman": "ka",
      "category": "consonant",
      "dots": [
        1,
        3
      ],
      "audio": "0012.mp3"
    },
    {
      "id": 12,
      "char": "খ",
      "name": "kha",
      "roman": "kha",
      "category": "consonant",
      "dots": [
        4,
        6
      ],
      "audio": "0013.mp3"
    },
    {
      "id": 13,
      "char": "গ",
      "name": "ga",
      "roman": "ga",
      "category": "consonant",
      "dots": [
        1,
        2,
        4,
        5
      ],
      "audio": "0014.mp3"
    },
    {
      "id": 14,
      "char": "ঘ",
      "name": "gha",
      "roman": "gha",
      "category": "consonant",
      "dots": [
        1,
        2,
        6
      ],
      "audio": "0015.mp3"
    },
    {
      "id": 15,
      "char": "ঙ",
      "name": "uma",
      "roman": "nga",
      "category": "consonant",
      "dots": [
        3,
        4,
        6
      ],
      "audio": "0016.mp3"
    },
    {
      "id": 16,
      "char": "চ",
      "name": "cha",
      "roman": "cha",
      "category": "consonant",
      "dots": [
        1,
        4
      ],
      "audio": "0017.mp3"
    },
    {
      "id": 17,
      "char": "ছ",
      "name": "chha",
      "roman": "chha",
      "category": "consonant",
      "dots": [
        1,
        6
      ],
      "audio": "0018.mp3"
    },
    {
      "id": 18,
      "char": "জ",
      "name": "ja",
      "roman": "ja",
      "category": "consonant",
      "dots": [
        2,
        4,
        5
      ],
      "audio": "0019.mp3"
    },
    {
      "id": 19,
      "char": "ঝ",
      "name": "jha",
      "roman": "jha",
      "category": "consonant",
      "dots": [
        3,
        5,
        6
      ],
      "audio": "0020.mp3"
    },
    {
      "id": 20,
      "char": "ঞ",
      "name": "nia",
      "roman": "nya",
      "category": "consonant",
      "dots": [
        2,
        5
      ],
      "audio": "0021.mp3"
    },
    {
      "id": 21,
      "char": "ট",
      "name": "tta",
      "roman": "ta",
      "category": "consonant",
      "dots": [
        2,
        3,
        4,
        5,
        6
      ],
      "audio": "0022.mp3"
    },
    {
      "id": 22,
      "char": "ঠ",
      "name": "ttha",
      "roman": "tha",
      "category": "consonant",
      "dots": [
        2,
        4,
        5,
        6
      ],
      "audio": "0023.mp3"
    },
    {
      "id": 23,
      "char": "ড",
      "name": "dda",
      "roman": "da",
      "category": "consonant",
      "dots": [
        1,
        2,
        4,
        6
      ],
      "audio": "0024.mp3"
    },
    {
      "id": 24,
      "char": "ঢ",
      "name": "ddha",
      "roman": "dha",
      "category": "consonant",
      "dots": [
        1,
        2,
        3,
        4,
        5,
        6
      ],
      "audio": "0025.mp3"
    },
    {
      "id": 25,
      "char": "ণ",
      "name": "nna",
      "roman": "na",
      "category": "consonant",
      "dots": [
        3,
        4,
        5,
        6
      ],
      "audio": "0026.mp3"
    },
    {
      "id": 26,
      "char": "ত",
      "name": "ta",
      "roman": "ta",
      "category": "consonant",
      "dots": [
        2,
        3,
        4,
        5
      ],
      "audio": "0027.mp3"
    },
    {
      "id": 27,
      "char": "থ",
      "name": "tha",
      "roman": "tha",
      "category": "consonant",
      "dots": [
        1,
        4,
        5,
        6
      ],
      "audio": "0028.mp3"
    },
    {
      "id": 28,
      "char": "দ",
      "name": "da",
      "roman": "da",
      "category": "consonant",
      "dots": [
        1,
        4,
        5
      ],
      "audio": "0029.mp3"
    },
    {
      "id": 29,
      "char": "ধ",
      "name": "dha",
      "roman": "dha",
      "category": "consonant",
      "dots": [
        2,
        3,
        4,
        6
      ],
      "audio": "0030.mp3"
    },
    {
      "id": 30,
      "char": "ন",
      "name": "na",
      "roman": "na",
      "category": "consonant",
      "dots": [
        1,
        3,
        4,
        5
      ],
      "audio": "0031.mp3"
    },
    {
      "id": 31,
      "char": "প",
      "name": "pa",
      "roman": "pa",
      "category": "consonant",
      "dots": [
        1,
        2,
        3,
        4
      ],
      "audio": "0032.mp3"
    },
    {
      "id": 32,
      "char": "ফ",
      "name": "pha",
      "roman": "pha",
      "category": "consonant",
      "dots": [
        1,
        2,
        4
      ],
      "audio": "0033.mp3"
    },
    {
      "id": 33,
      "char": "ব",
      "name": "ba",
      "roman": "ba",
      "category": "consonant",
      "dots": [
        1,
        2
      ],
      "audio": "0034.mp3"
    },
    {
      "id": 34,
      "char": "ভ",
      "name": "bha",
      "roman": "bha",
      "category": "consonant",
      "dots": [
        4,
        5
      ],
      "audio": "0035.mp3"
    },
    {
      "id": 35,
      "char": "ম",
      "name": "ma",
      "roman": "ma",
      "category": "consonant",
      "dots": [
        1,
        3,
        4
      ],
      "audio": "0036.mp3"
    },
    {
      "id": 36,
      "char": "য",
      "name": "ya",
      "roman": "ja",
      "category": "consonant",
      "dots": [
        1,
        3,
        4,
        5,
        6
      ],
      "audio": "0037.mp3"
    },
    {
      "id": 37,
      "char": "র",
      "name": "ra",
      "roman": "ra",
      "category": "consonant",
      "dots": [
        1,
        2,
        3,
        5
      ],
      "audio": "0038.mp3"
    },
    {
      "id": 38,
      "char": "ল",
      "name": "la",
      "roman": "la",
      "category": "consonant",
      "dots": [
        1,
        2,
        3
      ],
      "audio": "0039.mp3"
    },
    {
      "id": 39,
      "char": "শ",
      "name": "sha",
      "roman": "sha",
      "category": "consonant",
      "dots": [
        1,
        4,
        6
      ],
      "audio": "0040.mp3"
    },
    {
      "id": 40,
      "char": "ষ",
      "name": "ssa",
      "roman": "sha",
      "category": "consonant",
      "dots": [
        1,
        2,
        3,
        4,
        6
      ],
      "audio": "0041.mp3"
    },
    {
      "id": 41,
      "char": "স",
      "name": "sa",
      "roman": "sa",
      "category": "consonant",
      "dots": [
        2,
        3,
        4
      ],
      "audio": "0042.mp3"
    },
    {
      "id": 42,
      "char": "হ",
      "name": "ha",
      "roman": "ha",
      "category": "consonant",
      "dots": [
        1,
        2,
        5
      ],
      "audio": "0043.mp3"
    },
    {
      "id": 43,
      "char": "ড়",
      "name": "rra",
      "roman": "ra",
      "category": "consonant",
      "dots": [
        1,
        2,
        4,
        5,
        6
      ],
      "audio": "0044.mp3"
    },
    {
      "id": 44,
      "char": "ঢ়",
      "name": "rha",
      "roman": "rha",
      "category": "consonant",
      "dots": [
        1,
        2,
        3,
        5,
        6
      ],
      "audio": "0045.mp3"
    },
    {
      "id": 45,
      "char": "য়",
      "name": "yya",
      "roman": "ya",
      "category": "consonant",
      "dots": [
        2,
        3,
        5,
        6
      ],
      "audio": "0046.mp3"
    },
    {
      "id": 46,
      "char": "ৎ",
      "name": "khanda_ta",
      "roman": "t",
      "category": "consonant",
      "dots": [
        2,
        3,
        6
      ],
      "audio": "0047.mp3"
    },
    {
      "id": 47,
      "char": "ং",
      "name": "anushar",
      "roman": "ng",
      "category": "consonant",
      "dots": [
        5,
        6
      ],
      "audio": "0048.mp3"
    },
    {
      "id": 48,
      "char": "ঃ",
      "name": "bisharga",
      "roman": "h",
      "category": "consonant",
      "dots": [
        2,
        3
      ],
      "audio": "0049.mp3"
    },
    {
      "id": 49,
      "char": "ঁ",
      "name": "chandrabindu",
      "roman": "n",
      "category": "consonant",
      "dots": [
        4
      ],
      "audio": "0050.mp3"
    }
  ],
  "verified_count": 11
}
;
