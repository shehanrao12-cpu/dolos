use std::{fmt::Display, str::FromStr};

use hex;
use pallas::{crypto::hash::Hash, network::miniprotocols::Point as PallasPoint};
use regex::Regex;
use serde::{Deserialize, Serialize};

use crate::{Block, BlockHash, BlockSlot};

#[derive(Debug, Clone, Serialize, Deserialize, Eq)]
pub enum ChainPoint {
    Origin,
    Slot(BlockSlot),
    Specific(BlockSlot, BlockHash),
}

impl ChainPoint {
    pub fn slot(&self) -> BlockSlot {
        match self {
            Self::Origin => 0,
            Self::Slot(slot) => *slot,
            Self::Specific(slot, _) => *slot,
        }
    }

    pub fn hash(&self) -> Option<BlockHash> {
        match self {
            Self::Specific(_, hash) => Some(*hash),
            _ => None,
        }
    }

    /// Returns true if this point can be used as an intersection point.
    /// Origin and Specific points with non-zero hashes are fully defined;
    /// Slot-only points and zero-hash Specifics are not.
    pub fn is_fully_defined(&self) -> bool {
        match self {
            Self::Origin => true,
            Self::Specific(_, hash) => hash.as_slice() != [0u8; 32],
            Self::Slot(_) => false,
        }
    }
}

impl Display for ChainPoint {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Origin => write!(f, "Origin"),
            Self::Slot(slot) => write!(f, "{slot}"),
            Self::Specific(slot, hash) => write!(f, "{slot}({hash})"),
        }
    }
}

impl PartialEq for ChainPoint {
    fn eq(&self, other: &Self) -> bool {
        match (self, other) {
            (Self::Specific(l0, l1), Self::Specific(r0, r1)) => l0 == r0 && l1 == r1,
            (Self::Slot(l0), Self::Slot(r0)) => l0 == r0,
            (Self::Origin, Self::Origin) => true,
            // in the particular scenario where we are more specific than the other value, it's ok
            // to compare just slots. The inverse is not true (we're less specific than the other
            // value that requires also comparing hashes).
            (Self::Specific(l0, _), Self::Slot(r0)) => l0 == r0,
            _ => false,
        }
    }
}

impl Ord for ChainPoint {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        let l_slot = self.slot();
        let r_slot = other.slot();

        // if slots are different, we can compare them directly
        if l_slot != r_slot {
            return l_slot.cmp(&r_slot);
        }

        // if the slots are the same, we need to compare hashes

        let l_hash = self.hash();
        let r_hash = other.hash();

        l_hash.cmp(&r_hash)
    }
}

impl PartialOrd for ChainPoint {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}

impl From<PallasPoint> for ChainPoint {
    fn from(value: PallasPoint) -> Self {
        match value {
            PallasPoint::Origin => ChainPoint::Origin,
            PallasPoint::Specific(s, h) => ChainPoint::Specific(s, h.as_slice().into()),
        }
    }
}

impl TryFrom<ChainPoint> for PallasPoint {
    type Error = ();

    fn try_from(value: ChainPoint) -> Result<Self, Self::Error> {
        match value {
            ChainPoint::Origin => Ok(PallasPoint::Origin),
            ChainPoint::Specific(s, h) => Ok(PallasPoint::Specific(s, h.to_vec())),
            ChainPoint::Slot(_) => Err(()),
        }
    }
}

impl<T> From<&T> for ChainPoint
where
    T: Block,
{
    fn from(value: &T) -> Self {
        let slot = value.slot();
        let hash = value.hash();
        ChainPoint::Specific(slot, hash)
    }
}

impl ChainPoint {
    pub fn into_bytes(self) -> [u8; 40] {
        let slot = self.slot();

        let hash = match self.hash() {
            Some(hash) => *hash,
            None => [0u8; 32],
        };

        let mut out = [0u8; 40];
        out[0..8].copy_from_slice(&slot.to_be_bytes());
        out[8..40].copy_from_slice(hash.as_slice());
        out
    }

    const ORIGIN_BYTES: [u8; 40] = [0u8; 40];

    pub fn from_bytes(value: [u8; 40]) -> Self {
        if value == Self::ORIGIN_BYTES {
            return ChainPoint::Origin;
        }

        let slot_half: [u8; 8] = value[0..8].try_into().unwrap();
        let hash_half: [u8; 32] = value[8..40].try_into().unwrap();
        let slot = u64::from_be_bytes(slot_half);
        let hash = Hash::new(hash_half);
        ChainPoint::Specific(slot, hash)
    }
}

impl FromStr for ChainPoint {
    type Err = String;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        let s = s.trim();

        // Handle "Origin" case
        if s == "Origin" {
            return Ok(ChainPoint::Origin);
        }

        // Regex to match slot(hash) format where hash is 64 hex characters (32 bytes)
        let re = Regex::new(r"^(\d+)\(([0-9a-fA-F]{64})\)$").unwrap();

        if let Some(caps) = re.captures(s) {
            let slot: BlockSlot = caps[1].parse().map_err(|_| "invalid slot")?;
            let hash_bytes = hex::decode(&caps[2]).map_err(|_| "invalid hash")?;
            let hash_array: [u8; 32] = hash_bytes.try_into().map_err(|_| "invalid hash")?;
            let hash = Hash::new(hash_array);
            return Ok(ChainPoint::Specific(slot, hash));
        }

        // Try to parse as slot-only (no parentheses)
        if let Ok(slot) = s.parse::<BlockSlot>() {
            return Ok(ChainPoint::Slot(slot));
        }

        Err("invalid format".to_string())
    }
}

#[cfg(test)]
mod tests {
    use proptest::prelude::*;
    use proptest::proptest;

    use super::*;

    prop_compose! {
      fn any_hash() (bytes in any::<[u8; 32]>()) -> Hash<32> {
            Hash::new(bytes)
        }
    }

    prop_compose! {
      fn any_specific_point() (slot in any::<BlockSlot>(), hash in any_hash()) -> ChainPoint {
            ChainPoint::Specific(slot, hash)
        }
    }

    proptest! {
        #[test]
        fn test_binary_order_is_maintained(point1 in any_specific_point(), point2 in any_specific_point()) {
            let bytes1 = point1.clone().into_bytes();
            let bytes2 = point2.clone().into_bytes();

            let point_cmp = point1.cmp(&point2);
            let bytes_cmp = bytes1.cmp(&bytes2);

            assert_eq!(point_cmp, bytes_cmp);
        }
    }

    #[test]
    fn test_from_str_origin() {
        assert_eq!("Origin".parse::<ChainPoint>().unwrap(), ChainPoint::Origin);
    }

    #[test]
    fn test_from_str_slot_only() {
        assert_eq!(
            "12345".parse::<ChainPoint>().unwrap(),
            ChainPoint::Slot(12345)
        );
    }

    #[test]
    fn test_from_str_slot_hash() {
        let hash_bytes = [1u8; 32];
        let hash_hex = hex::encode(hash_bytes);
        let input = format!("12345({})", hash_hex);

        let result: ChainPoint = input.parse().unwrap();
        match result {
            ChainPoint::Specific(slot, hash) => {
                assert_eq!(slot, 12345);
                assert_eq!(hash.as_slice(), &hash_bytes);
            }
            _ => panic!("Expected Specific variant"),
        }
    }

    #[test]
    fn test_from_str_invalid() {
        assert!("invalid".parse::<ChainPoint>().is_err());
        assert!("12345(invalid)".parse::<ChainPoint>().is_err());
        assert!("12345(short)".parse::<ChainPoint>().is_err());
    }

    #[test]
    fn test_slot_and_hash_accessors() {
        let hash = Hash::new([7u8; 32]);

        assert_eq!(ChainPoint::Origin.slot(), 0);
        assert_eq!(ChainPoint::Origin.hash(), None);

        assert_eq!(ChainPoint::Slot(42).slot(), 42);
        assert_eq!(ChainPoint::Slot(42).hash(), None);

        assert_eq!(ChainPoint::Specific(42, hash).slot(), 42);
        assert_eq!(ChainPoint::Specific(42, hash).hash(), Some(hash));
    }

    #[test]
    fn test_is_fully_defined() {
        // Origin is always a valid intersection point.
        assert!(ChainPoint::Origin.is_fully_defined());

        // Slot-only points lack a hash, so they can never be fully defined.
        assert!(!ChainPoint::Slot(42).is_fully_defined());

        // A Specific with a real hash is fully defined.
        assert!(ChainPoint::Specific(42, Hash::new([1u8; 32])).is_fully_defined());

        // A Specific carrying the all-zero "synthetic" hash is NOT fully
        // defined: this is the sentinel used by reset_to / epoch boundaries
        // and must not be treated as a real intersection point.
        assert!(!ChainPoint::Specific(42, Hash::new([0u8; 32])).is_fully_defined());
    }

    #[test]
    fn test_into_bytes_origin_is_all_zero() {
        assert_eq!(ChainPoint::Origin.into_bytes(), [0u8; 40]);
    }

    #[test]
    fn test_from_bytes_all_zero_is_origin() {
        assert_eq!(ChainPoint::from_bytes([0u8; 40]), ChainPoint::Origin);
    }

    #[test]
    fn test_specific_bytes_roundtrip() {
        let point = ChainPoint::Specific(123_456_789, Hash::new([9u8; 32]));
        assert_eq!(ChainPoint::from_bytes(point.clone().into_bytes()), point);
    }

    #[test]
    fn test_slot_only_serializes_with_zero_hash() {
        // A Slot-only point has no hash, so its byte form carries the zero
        // sentinel and decodes back as a Specific with the synthetic hash.
        // The WAL relies on this (it skips synthetic zero-hash entries).
        let bytes = ChainPoint::Slot(42).into_bytes();
        assert_eq!(&bytes[8..40], &[0u8; 32]);
        assert_eq!(
            ChainPoint::from_bytes(bytes),
            ChainPoint::Specific(42, Hash::new([0u8; 32]))
        );
    }

    #[test]
    fn test_ordering_by_slot_then_hash() {
        let low_slot = ChainPoint::Specific(1, Hash::new([0xff; 32]));
        let high_slot = ChainPoint::Specific(2, Hash::new([0x00; 32]));
        // Slot dominates the ordering regardless of hash bytes.
        assert!(low_slot < high_slot);

        // Within the same slot, ordering falls back to the hash.
        let small_hash = ChainPoint::Specific(5, Hash::new([0x00; 32]));
        let big_hash = ChainPoint::Specific(5, Hash::new([0x01; 32]));
        assert!(small_hash < big_hash);
    }

    #[test]
    fn test_asymmetric_equality_is_intentional() {
        // INTENTIONAL: a more-specific point may match a less-specific one by
        // slot alone (used for chain intersection). This makes PartialEq
        // deliberately asymmetric; the test guards that behavior so it isn't
        // "fixed" by accident, which would break intersection matching.
        let specific = ChainPoint::Specific(7, Hash::new([3u8; 32]));
        let slot_only = ChainPoint::Slot(7);
        assert_eq!(specific, slot_only);
        assert_ne!(slot_only, specific);
    }

    #[test]
    fn test_slot_try_into_pallas_point_fails() {
        // A Slot-only point cannot become a Pallas Point (no hash).
        let result: Result<PallasPoint, ()> = ChainPoint::Slot(42).try_into();
        assert!(result.is_err());
    }

    proptest! {
        #[test]
        fn test_specific_bytes_roundtrip_prop(point in any_specific_point()) {
            // Skip the single ambiguous value (slot 0 + zero hash) that aliases
            // the Origin sentinel; every other Specific must round-trip exactly.
            prop_assume!(point.clone().into_bytes() != ChainPoint::ORIGIN_BYTES);
            prop_assert_eq!(ChainPoint::from_bytes(point.clone().into_bytes()), point);
        }

        #[test]
        fn test_display_fromstr_roundtrip_specific(point in any_specific_point()) {
            let rendered = point.to_string();
            let parsed: ChainPoint = rendered.parse().unwrap();
            prop_assert_eq!(parsed, point);
        }
    }
}
