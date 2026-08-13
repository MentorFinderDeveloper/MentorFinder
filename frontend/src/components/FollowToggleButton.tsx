import { CSSProperties } from "react";

interface FollowToggleButtonProps {
    followed: boolean;
    loading: boolean;
    disabled?: boolean;
    onClick: () => void;
    followedLabel?: string;
    className?: string;
    style?: CSSProperties;
}

const FollowToggleButton = ({
    followed,
    loading,
    disabled = false,
    onClick,
    followedLabel,
    className,
    style,
}: FollowToggleButtonProps) => {
    // Allow callers to override only the "followed" copy while keeping the default action labels.
    const label = followed ? (followedLabel ?? "取消关注") : "关注";

    return (
        <button
            type="button"
            className={className}
            style={style}
            onClick={onClick}
            disabled={disabled || loading}
            aria-busy={loading}
        >
            <span>{label}</span>
            {/* Preserve the button width while showing a loading overlay during follow/unfollow requests. */}
            {loading && <span aria-hidden="true" className="followToggleButtonOverlay" />}
        </button>
    );
};

export default FollowToggleButton;
